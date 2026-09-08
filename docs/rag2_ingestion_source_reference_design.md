# RAG 2.0 文档摄入与来源回链接入设计（第 2 周 Day 1）

## 1. 设计结论

新文档摄入链路不直接替换当前主 Agent 的知识库检索。第一阶段采用**并行接入、默认关闭、可回退**的方式：

```text
现有 Markdown 主链路
  backend/data/docs/*.md
  → search_knowledge_base()
  → search_vector_store() fallback
  → 既有 rules / LangGraph Agent

RAG 2.0 新摄入链路（默认不参与回答）
  受管本地文件
  → ingest_document()
  → SQLite 文档版本与 Chunk 元数据
  → 后续独立索引 / 检索入口
  → feature flag 开启后才可成为候选来源
```

这样可以保留现有 31 条主链路黄金集的稳定性，也让新链路能够独立验证解析、版本、来源和检索质量。

## 2. 当前代码事实

| 当前模块 | 现有职责 | RAG 2.0 接入时的限制 |
| --- | --- | --- |
| `app/knowledge_base.py` | 直接读取 `backend/data/docs/*.md`，按行切块并做关键词检索 | 没有上传、文档 ID、版本、页码或解析状态 |
| `app/vector_store.py` | 将旧 Markdown Chunk 写入 Chroma；metadata 仅含 `file`、`chunk_id` | 无法区分版本、标题路径和页码 |
| `app/models.py` 的 `Source` | 返回 `file`、`snippet`、`score`、`chunk_id` | 无法把回答精确回链到文档版本、标题和页码 |
| `app/database.py` | 初始化会话、待确认操作、工单表 | 尚无文档、版本、解析或 Chunk 元数据表 |
| `app/tool_registry.py` | 为 rules / LangGraph 暴露 `search_knowledge_base`、`search_vector_store` | 新检索入口不能悄悄替换已有工具的返回语义 |

第 1 周新增的 `knowledge_models.py`、`document_parser.py`、`document_chunker.py` 只在 isolated synthetic 评测中使用，尚未接入上述主链路。

## 3. 最小生命周期与状态边界

第 2 周先采用受管本地目录保存原文件；MinIO 属于第 5 周的替换点，而不是本周前置依赖。

```text
受管原文件
  → 计算 SHA-256
  → 创建或复用逻辑文档
  → 创建 UPLOADED 版本
  → 解析
  → 切块
  → 持久化元数据
  → （后续）写入独立索引
  → 可检索
```

建议的版本状态：

| 状态 | 含义 | 是否生成 Chunk | 是否允许检索 |
| --- | --- | ---: | ---: |
| `UPLOADED` | 已接收文件，尚未开始解析 | 否 | 否 |
| `PARSING` | 正在调用 Parser | 否 | 否 |
| `PARSED` | 已得到 `ParsedDocument`；若 Chunk 已持久化，其 index status 仍为 `PENDING` | 可能为是 | 否 |
| `INDEXING` | 正在写入检索索引 | 是 | 否 |
| `INDEXED` | 索引及元数据均完成 | 是 | 是 |
| `FAILED` | 解析、切块或索引失败 | 否或清理后为否 | 否 |
| `SUPERSEDED` | 已被同一逻辑文档的新版本替代 | 保留 | 否，除非未来显式支持历史检索 |

关键约束：

1. `FAILED` 版本不应残留可检索 Chunk 或向量；扫描 PDF 的 OCR 待处理属于不可检索状态。
2. 相同内容 hash 重复导入时，应复用现有版本，而不是重复创建 Chunk 和索引。
3. 同一逻辑文档的新 hash 应创建新版本；只有新版本索引成功后才把旧版本标记为 `SUPERSEDED`。
4. 切块或索引中途失败时，需要删除本次版本产生的 Chunk / 向量，或使其永远不满足 `INDEXED` 查询条件。

## 4. SQLite 最小数据模型

第 2 周无需引入新数据库。先在现有 SQLite 中增加三个表，原会话和工单表保持不变。

### `knowledge_documents`

保存逻辑文档身份，不保存每次上传的具体内容。这里的 `logical_document_id` 与第 1 周 `Document.document_id` 不同：前者表示“同一份制度 / SOP”，后者表示“该制度的一个具体版本”。保留这一层可以兼容已有 `previous_version_document_id` 关系，不必重写数据契约。

```text
logical_document_id  TEXT PRIMARY KEY
display_name         TEXT NOT NULL
source_type          TEXT NOT NULL       -- synthetic / public / user_authorized
active_document_id   TEXT NULL            -- 指向当前可检索的具体 Document ID
created_at           TEXT NOT NULL
updated_at           TEXT NOT NULL
```

### `knowledge_document_versions`

保存一次内容版本、解析结果和处理状态。

```text
document_id          TEXT PRIMARY KEY     -- 具体版本，匹配 Document.document_id
logical_document_id  TEXT NOT NULL
version              TEXT NOT NULL
previous_document_id TEXT NULL
content_hash         TEXT NOT NULL
source_path          TEXT NOT NULL       -- 第 2 周受管本地路径；第 5 周替换为 object_key
document_format      TEXT NOT NULL
parse_status         TEXT NOT NULL
ingestion_status     TEXT NOT NULL
parser_name          TEXT NULL
parser_version       TEXT NULL
parsed_document_id   TEXT NULL
markdown_content     TEXT NULL
page_map_json        TEXT NOT NULL
parse_warnings_json  TEXT NOT NULL
created_at           TEXT NOT NULL
indexed_at           TEXT NULL
UNIQUE (logical_document_id, version)
UNIQUE (logical_document_id, content_hash)
```

### `knowledge_chunks`

保存可回链的 Parent / Child Chunk 元数据与文本；后续写 Chroma 时使用同一个 `chunk_id`。

```text
chunk_id             TEXT PRIMARY KEY
document_id          TEXT NOT NULL
document_version     TEXT NOT NULL
kind                 TEXT NOT NULL       -- parent / child
parent_chunk_id      TEXT NULL
heading_path_json    TEXT NOT NULL
page_start           INTEGER NULL
page_end             INTEGER NULL
content              TEXT NOT NULL
content_hash         TEXT NOT NULL
created_at           TEXT NOT NULL
```

其中 `knowledge_document_versions` 是状态与一致性边界；`knowledge_chunks` 是来源回链和检索 metadata 的事实来源。不要把完整解析产物、Chunk、版本信息只存进 Chroma metadata，因为后续删除、重建和审计会难以治理。

## 5. 模块职责与接口边界

```text
routers/knowledge_documents.py
  HTTP 参数校验、上传或本地导入请求、查询状态
        ↓
knowledge_ingestion_service.py
  幂等判断、状态流转、事务边界、调用 Parser / Chunker / Indexer
        ↓
document_parser.py + document_chunker.py
  纯内容处理；不读写 SQLite、Chroma 或 FastAPI Request
        ↓
knowledge_repository.py
  SQLite 的 documents / versions / chunks 持久化
        ↓
knowledge_index.py（后续实现）
  将有效 Child Chunk 写入独立 collection；支持按 document_id/version 删除
```

Day 2 的最小入口应优先是内部 Python 服务函数：

```python
def ingest_document(
    source_path: Path,
    source_type: SourceType,
    logical_document_id: str | None = None,
) -> IngestionResult:
    ...
```

先用受控本地文件调用它并建立自动测试，再决定是否暴露 `POST /knowledge/documents`。这样可以避免上传协议、文件大小、鉴权和对象存储问题掩盖解析与版本逻辑本身。

## 6. 来源回链的兼容设计

现有 `Source` 不能直接删字段或修改已有语义，因为 rules Agent、LangGraph Agent、SSE 响应和前端都依赖它。

第 2 周推荐只增加可选字段：

```text
document_id: str | None
document_version: str | None
heading_path: list[str] | None
page_start: int | None
page_end: int | None
```

兼容规则：

| 来源类型 | 原字段 | 新字段 |
| --- | --- | --- |
| 旧 Markdown 主链路 | 保持 `file`、`snippet`、`score`、`chunk_id` | 全部为 `null` |
| RAG 2.0 新摄入文档 | 继续填充旧字段，保证前端兼容 | 按 Chunk 元数据填充版本、标题路径、页码 |

新链路的最终引用应该能表达为：

```text
文件：身份与访问管理制度.pdf
版本：2.0
章节：账号申请 > 管理员审批
页码：第 3 页
Chunk：chunk_xxx
```

## 7. 检索接入与回退策略

第 2 周不修改 `search_knowledge_base()` 的默认行为，也不覆盖 `search_vector_store()` 的现有 collection。

后续新增独立入口，例如：

```text
search_ingested_knowledge()
  仅查询 ingestion_status = INDEXED 的新 Child Chunk
  仅返回 active_version 对应的文档
  返回可构造扩展 Source 的 RetrievalResult
```

开关策略：

```text
KNOWLEDGE_RETRIEVER=legacy              # 默认；维持当前主链路
KNOWLEDGE_RETRIEVER=ingested_experiment # 仅本地或测试环境启用
```

若新检索入口异常、空结果、来源字段不完整或指标回归，则关闭开关并立即回退 legacy 链路。是否让新旧链路同时召回、如何融合，留到第 3 周消融实验；第 2 周只保证新链路正确、可回链、可删除和可隔离。

## 8. 第 2 周分日实施顺序

| 日程 | 目标 | 最小可验证产出 |
| --- | --- | --- |
| Day 1（本设计） | 明确数据、状态、模块和兼容边界 | 本设计文档；不改线上检索 |
| Day 2 | 实现 SQLite repository 与 `ingest_document()` | Markdown、文本型 PDF 各导入一份；重复 hash 幂等 |
| Day 3 | 持久化 Parent / Child Chunk，并保证版本过滤 | 新 Chunk 带完整来源字段；旧版本不可作为 active 候选 |
| Day 4 | 加独立 `search_ingested_knowledge()` 和扩展 `Source` | 能返回文件、版本、章节、页码；旧 API 兼容 |
| Day 5 | 选择 3—5 份复杂 PDF，对比基础解析与 MinerU | 结构、表格、页码、耗时、检索质量对照 |
| Day 6 | 补失败 / 幂等 / 版本 / 来源回链测试 | 至少 5 条测试；周复盘 |

## 9. Day 2 开始前的验收清单

在创建新表或改动 API 前，必须先确认：

1. 旧 `backend/data/docs/*.md` 与 31 条主链路回归保持不变。
2. SQLite schema 初始化具有幂等性，不能破坏已有会话、确认和工单数据。
3. 版本、状态与来源字段不只存在于 Chroma，而能从 SQLite 独立审计。
4. 解析失败、索引失败、重复导入和新版本替代均有可测试的预期行为。
5. 新能力默认关闭，并存在明确的 legacy 回退路径。

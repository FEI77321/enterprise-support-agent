# Enterprise Support Agent RAG 2.0：3—5 分钟演示稿

> 目标：讲清“原系统为什么需要这次增强、我做了什么、如何证明可靠、为什么没有过度工程”。
>
> 使用方法：第一次按 5 分钟版完整练习；熟悉后压缩为 3 分钟版。演示时不要临时打开实验开关或修改代码，优先使用已有截图、评测输出和 README 架构图。

## 0. 开场（20 秒）

> 我做的是 Enterprise Support Agent，面向企业内部 IT 支持场景。原项目已经支持 Markdown 知识库问答、ChromaDB 向量 fallback、工单流转和 LLM 引用校验。这次我没有简单再堆一个模型或向量库，而是补了一条受控的 RAG 2.0 文档摄入链路，解决文档版本、解析失败、来源回链和安全接入的问题。

## 1. 原系统问题与目标（35 秒）

> 原来的检索能从静态 Markdown 中找答案，但对“同一制度更新了 v2 怎么切换”“扫描件没解析出文字怎么办”“回答具体来自文件哪一版、哪一页”没有独立、可验证的治理闭环。这个缺口的风险是：旧版本可能继续被引用，解析失败文档可能变成空证据，用户也无法核实答案出处。
>
> 所以我把目标收敛为最小闭环：受管文件进入系统后，要能幂等识别、版本切换、失败隔离、分块、检索，并返回可追溯来源；同时必须不影响已经稳定的旧 Agent 主链路。

## 2. 核心设计与代码落点（70 秒）

演示时可打开 [RAG 2.0 架构图](rag2_architecture.md)。

> 文档进入链路是：`Path → SHA-256 → Parser → Parent/Child Chunker → SQLite Repository`。我把“同一个业务制度”与“某一次具体文档版本”分开：同 hash 的重导入会复用已有版本；新成功版本激活后，旧 active 版本变成 `SUPERSEDED`；扫描件或不可读 PDF 会记录为 `FAILED`，但不会生成 Chunk。
>
> 在检索侧，我新建的是隔离 SQLite 词面检索，只允许 active 文档且 `INDEXED` 的 Child Chunk 进入候选池。这里的 `INDEXED` 只代表可被这条 SQLite 实验检索使用，不代表已经向量化或写入 ChromaDB。
>
> 返回结果会适配到原有 `Source` 模型，除文件、chunk、分数外，还能带版本、标题路径、页码和 Parent Chunk 上下文 ID。Markdown 有可靠标题路径；PDF 只返回实际能保证的文件、版本和页码，不从视觉排版猜标题。

可在讲解时指出这些文件：

```text
backend/app/knowledge_ingestion_service.py   # ingest_document()
backend/app/knowledge_repository.py          # version / active / indexed 语义
backend/app/document_parser.py                # Markdown、文本型 PDF、失败隔离
backend/app/document_chunker.py               # Parent / Child 分块
backend/app/ingested_knowledge_retriever.py  # 隔离检索
backend/app/knowledge_source_adapter.py       # RetrievalResult → Source
```

## 3. 如何安全接入 Agent（45 秒）

> 我没有把新检索替换成主检索。它被 `INGESTED_KNOWLEDGE_EXPERIMENT_ENABLED=false` 默认关闭。开关关闭时，Agent 不会访问实验数据库；开关开启后，也只会在旧关键词检索没有结果时尝试新链路。如果新链路命中，会返回带来源的实验答案；如果无结果或发生异常，则继续原有的 ChromaDB 向量 fallback、澄清或建单流程。
>
> 这样做的好处是把实验的影响面压到最小：已有高置信回答不会被覆盖，出现问题可以一键关闭，而且我只在 rules Agent 中接入，没有为了实验再维护一套 LangGraph 分支。

## 4. 证据与指标（65 秒）

> 我把验证拆成多层契约，而不是只做一次手动聊天。摄入契约 5/5 覆盖 Markdown、文本 PDF、同 hash 幂等、扫描件失败隔离和 v2 替代 v1；来源回链契约 3/3；active / indexed 检索准入契约 3/3；feature flag 接入契约 2/2。默认关闭时，旧主链路固定集仍保持 Recall@3 1.0000、FPR 0、MRR@3 0.9551、nDCG@3 0.9602。
>
> 此前在 synthetic 固定集的 document-aware lexical 实验中，Recall@3 从 0.9375 提升到 1.0000，MRR@3 从 0.9062 提升到 0.9271，nDCG@3 从 0.9144 提升到 0.9457，FPR 没有增加。我的表述会严格限定为“synthetic 固定集上的隔离实验结果”，不会说成线上效果。

## 5. 复杂 PDF 与技术取舍（35 秒）

> 我还用两份表格 PDF 做了 5 次 `pypdf` 基线。文本事实锚点均为 5/5，页码可用，平均解析大约 4.673ms 和 3.661ms；但表格行列结构不能保留。MinerU 能补这个缺口，但当前是 Windows + Python 3.13，官方 Windows 支持范围不匹配，完整接入还需要独立环境、依赖和模型。没有真实表格单元格级问答需求时，我选择记录边界并保留升级条件，而不是为了技术栈强接。

## 6. 收尾（20 秒）

> 这次 RAG 2.0 的重点是把“检索到内容”升级为“可治理、可回链、可回退的证据链”。我没有把未验证的实验直接替换主链路，而是通过版本治理、失败隔离、默认关闭开关和独立评测逐步缩小风险。未来如果拿到真实授权文档和明确的吞吐、表格或 OCR 需求，再基于同一套评测框架决定是否接向量化或复杂解析器。

## 3 分钟压缩版提示卡

```text
原问题：静态知识库缺少版本、失败隔离、页码来源。
方案：hash 幂等 + Parser + Parent/Child + SQLite 版本治理 + active/indexed 检索 + Source 回链。
安全：默认 false；仅旧关键词无结果时尝试；异常回旧向量 fallback；只接 rules Agent。
证据：摄入 5/5，来源 3/3，检索 3/3，开关 2/2；旧主链路 Recall 1.0、FPR 0。
取舍：synthetic 策略指标提升，不等于线上；pypdf 文本/页码足够，表格/OCR 不强接 MinerU；不迁移 Milvus。
```

## 演示后的高频追问

| 面试官可能追问 | 立即跳转 |
| --- | --- |
| 为什么不直接接入主链路？ | [题卡 5](rag2_interview_cards.md#5-为什么指标变好仍然不立即接入主-agent) |
| 为什么不用 MinerU / OCR？ | [题卡 6](rag2_interview_cards.md#6-为什么不直接上-mineru--ocr) |
| 为什么仍然用 Chroma？ | [ADR-0001](adr/0001-keep-chroma-as-primary-vector-store.md) |
| 版本和来源如何保证？ | [架构说明](rag2_architecture.md#3-文档状态与准入语义) |
| 指标是否可信？ | [题卡 4](rag2_interview_cards.md#4-指标相比基线提升了什么) |

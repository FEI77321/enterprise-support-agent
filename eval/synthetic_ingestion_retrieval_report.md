# Synthetic 文档摄入与检索实验报告（v1）

## 1. 实验目的与边界

本报告验证 Enterprise Support Agent RAG 2.0 的新文档摄入原型是否能形成一个可评测闭环：

```text
synthetic Markdown / PDF
  → 统一解析状态与页码映射
  → 标题感知 Parent / Child Chunk
  → 版本过滤后的候选池
  → isolated lexical 检索策略对比
  → 自动回归契约
```

本报告的结果仅适用于隔离的 synthetic 语料和 `eval/` 实验路径。它不替代当前主 Agent 的 `search_knowledge_base()` 或 Chroma fallback，也不能直接与原有 31 条主链路黄金集的指标横向比较。

## 2. 固定数据与评测口径

| 项目 | 固定值 |
| --- | --- |
| 语料版本 | `enterprise_support_synthetic_v1` |
| 文档数量 | 11 份 synthetic 文档 |
| 文档构成 | 5 份 Markdown、3 份文本型 PDF、2 份表格 PDF、1 份图片型扫描 PDF |
| 版本关系 | 含同一制度的 v1 / v2；检索时排除已被新版本替代的文档 |
| 黄金集 | `synthetic_golden_cases_v1.json`，18 条用例 |
| 可回答用例 | 16 条 |
| OCR 用例 | 1 条 |
| 拒答用例 | 1 条 |
| 检索粒度 | 版本有效且解析成功的 Child Chunk |
| 活跃候选数 | 20 个 Child Chunk |
| Top K | 3 |
| 最低词法分数 | 2.0 |

评估使用动态 ground truth：根据用例绑定的 `document_id`、版本、页码和事实锚点，在每次运行时解析出相关 Child Chunk ID。因此，切块 ID 随实现调整变化时，评测不会因硬编码旧 ID 而产生伪失败。

## 3. 摄入与数据契约验证

| 能力 | 验证脚本 | 结果 |
| --- | --- | --- |
| 知识对象契约 | `run_knowledge_models_contract_eval.py` | Passed 4/4 |
| Markdown / PDF 解析 | `run_document_parser_eval.py` | Passed 3/3 |
| 标题感知父子分块 | `run_document_chunker_contract_eval.py` | Passed 4/4 |
| 检索 ground truth 就绪性 | `run_synthetic_retrieval_ready_contract.py` | Passed 16/16 |
| 文档感知检索回归 | `run_synthetic_document_aware_retrieval_contract.py` | Passed |

摄入基线结果：11 份文档中 10 份解析成功，图片型扫描 PDF 明确进入 `FAILED` 状态并携带 OCR 提示；它不会生成 Chunk，也不会进入检索候选池。

## 4. 策略定义

两种策略都只使用内存中的 active Child Chunk，不调用主 Agent、不读写 Chroma。

| 策略 | 实现 | 过程 |
| --- | --- | --- |
| `global_child_lexical` | `search_synthetic_chunks()` | 所有 Child Chunk 全局词法打分，直接取 Top 3 |
| `document_aware_lexical` | `search_synthetic_chunks_document_aware()` | 每篇文档聚合最高两个正分 Chunk 的证据，先选前 2 篇候选文档，再对其中 Child Chunk 排序取 Top 3 |

## 5. 评测结果

| 指标 | 全局 Child Chunk 策略 | 文档感知策略 | 变化 |
| --- | ---: | ---: | ---: |
| Macro Recall@3 | 0.9375 | **1.0000** | **+0.0625** |
| Macro MRR@3 | 0.9062 | **0.9271** | **+0.0209** |
| Macro nDCG@3 | 0.9144 | **0.9457** | **+0.0313** |
| False Positive Rate@3 | 0.0000 | **0.0000** | 0.0000 |
| OCR 候选池隔离 | Passed 1/1 | **Passed 1/1** | 保持通过 |

在相同语料、相同 Top K、相同最低分数和相同动态 ground truth 下，文档感知策略提升了召回与排序质量，同时未增加拒答误命中，也未让扫描 PDF 进入检索候选池。

## 6. 关键 bad case 与解释

### `syn_001`：跨章节证据分散

问题包含“笔记本”等范围信息，以及“金额阈值 / 审批人”等具体规则。它们分散在同一文档的不同章节中：全局策略会让范围章节或其他词面相似 Chunk 抢占 Top 3，导致包含关键阈值的 Chunk 落出结果。

文档感知策略利用同一文档多个 Chunk 的累计证据，成功把正确文档纳入候选，再使正确 Chunk 进入 Top 3。因此该用例从未完整召回变为 Recall@3 = 1.0。但它当前排第 3，仍有排序优化空间。

### `syn_004`：P1 事件语义重叠

正确制度 Chunk 与 P1 事故手册同时包含事件、时限和恢复等强词法特征。正确 Chunk 已进入 Top 3，但目前排第 2，说明文档级候选筛选解决了文档召回问题，尚未完全解决细粒度语义排序问题。

## 7. 自动回归门禁

`run_synthetic_document_aware_retrieval_contract.py` 会执行文档感知策略，并自动断言：

```text
answer_case_count         == 16
Macro Recall@3            >= 1.0000
Macro MRR@3               >= 0.9270
Macro nDCG@3              >= 0.9450
False Positive Rate@3     <= 0.0000
OCR candidate-pool isolation 必须通过
```

这使后续修改解析、分块或检索逻辑后能够自动发现效果退化；阈值来自本固定语料的当前基线，并不代表真实线上质量承诺。

## 8. 当前决策与未解决问题

### 当前决策

保留 `document_aware_lexical` 作为 RAG 2.0 摄入原型的候选检索策略和回归对象；暂不接入主 Agent。

原因是它在本固定实验中有明确收益，但缺少真实主链路接入、来源回链展示、延迟数据和更复杂文档对照。按照质量闸门，未完成这些条件前不能替换已有检索路径。

### 未解决问题

1. 尚未测量解析、切块和检索的 P50 / P95 延迟。
2. 尚未对复杂 PDF 进行基础解析器与 MinerU 的质量、耗时和成本对照。
3. 文档感知策略仅做候选文档选择，`syn_001` 和 `syn_004` 的 Top 1 排序问题仍待后续细粒度排序实验处理。
4. 新数据契约与 Chunk 尚未接入 SQLite、Chroma、FastAPI 和最终回答 `Source`。
5. 语料均为 synthetic，不能声称已经验证真实企业文档的线上效果。

## 9. 可复现命令

在项目根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe .\eval\run_knowledge_models_contract_eval.py
.\backend\.venv\Scripts\python.exe .\eval\run_document_parser_eval.py
.\backend\.venv\Scripts\python.exe .\eval\run_document_chunker_contract_eval.py
.\backend\.venv\Scripts\python.exe .\eval\run_synthetic_retrieval_ready_contract.py
.\backend\.venv\Scripts\python.exe .\eval\run_synthetic_lexical_retrieval_eval.py --strategy global_child_lexical
.\backend\.venv\Scripts\python.exe .\eval\run_synthetic_lexical_retrieval_eval.py --strategy document_aware_lexical
.\backend\.venv\Scripts\python.exe .\eval\run_synthetic_document_aware_retrieval_contract.py
```

## 10. 60 秒项目口述

> 我在 Enterprise Support Agent 的 RAG 2.0 升级里，没有直接把 PDF 解析或新的检索策略接到线上链路，而是先构造了一套明确标注为 synthetic 的固定语料，覆盖 Markdown、文本型 PDF、表格 PDF、扫描件和版本替代。随后我定义了 Document、ParsedDocument、KnowledgeChunk 和 RetrievalResult 的数据契约，把解析失败的扫描件明确隔离，避免空文本污染索引。在检索侧，我发现全局 Child Chunk 排序会遗漏跨章节分散的证据，所以实现了先聚合文档内局部证据、再排序 Chunk 的 document-aware 策略。在固定 16 个可回答用例上，Recall@3 从 0.9375 提升到 1.0000，MRR@3 从 0.9062 提升到 0.9271，nDCG@3 从 0.9144 提升到 0.9457，且 FPR 仍为 0。这个策略现在受自动回归契约保护，但我没有直接替换主 Agent，因为来源回链、复杂 PDF 对照和延迟数据还没有完成。

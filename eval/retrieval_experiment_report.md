# RAG 检索升级实验报告

## 实验目的

在固定黄金集和评估口径下，对比关键词检索、中文 BGE 向量检索、RRF 混合检索及 RRF + reranker 的效果，决定哪些方案进入主链路。

## 固定实验条件

- 黄金集：`eval/rag_eval_cases.json`，31 条用例。
- 评估范围：26 条正例，`Top-k = 3`。
- 指标：Macro Recall@3、MRR@3、nDCG@3。
- 文档与 chunk：所有方案使用同一份 Markdown 文档与同一套子块 ID。
- BGE 模型：`BAAI/bge-small-zh-v1.5`，模型缓存目录为 `D:\AI-Model-Cache\huggingface\`。
- RRF：关键词与 BGE 各召回 Top-10，使用 `RRF_K = 60` 融合后取 Top-3。

## 实验结果

| 方案 | Recall@3 | MRR@3 | nDCG@3 | 结论 |
| --- | ---: | ---: | ---: | --- |
| 关键词主检索 | 1.0000 | **0.9533** | **0.9586** | 当前主检索，排序最佳 |
| Chroma 默认 embedding | 0.6154 | 0.4359 | 0.4713 | 中文语义效果较弱 |
| BGE 向量检索 | 0.9231 | 0.8333 | 0.8562 | 显著优于默认 embedding |
| 关键词 + BGE RRF | **1.0000** | 0.9038 | 0.9226 | 召回完整，但排序略弱于关键词 |
| RRF + bge-reranker-base | **1.0000** | 0.8590 | 0.8892 | 本轮未带来排序提升 |

## 关键发现

1. 默认 Chroma embedding 对中文问题的向量检索效果不足；更换为 `bge-small-zh-v1.5` 后，Recall@3 从 `0.6154` 提升到 `0.9231`。
2. BGE 单路仍遗漏了两类问题：错误码 `691`（`rag_013`）和“先检查什么”的步骤顺序意图（`rag_025`）。
3. RRF 融合后，以上两条 bad case 都能在 Top-3 找回，Recall@3 达到 `1.0000`。
4. 关键词检索已经包含错误码、首步、排障和优先级等业务加权规则，在当前小型黄金集上排序最强。
5. reranker 面对较长且内容重复的父块上下文时，未能超过现有关键词排序；不应仅因引入模型而替换更优方案。

## 当前决策

```text
主检索：search_knowledge_base()
向量实验索引：bge-small-zh-v1.5 独立 collection
RRF / reranker：保留为实验能力，不接入主 Agent 主路径
```

保留 BGE 和 RRF 的实现，后续当知识库规模、同义表达和跨文档问题增加时，使用同一黄金集重新评估；只有 MRR、nDCG 或关键 bad case 确实改善，才接入主链路。

## 生成侧质量评测

### 自动检查

`eval/run_answer_quality_auto_eval.py` 已对 26 条应回答样本完成自动检查，结果为 `26/26` 通过。自动检查覆盖：

- Agent 最终响应类型为 `answer`；
- 回答文本非空；
- API 返回至少一条 source；
- 回答正文至少引用一条 API source；
- 父块样本引用黄金集指定的 `expected_context_chunk_id`；
- 流程/规则摘要样本包含黄金集定义的关键内容。

该检查曾发现 `rag_010`（“虚拟网卡驱动”）在高置信向量命中时仍返回 `clarify`。已为普通 Agent 和 LangGraph 增加 `vector_answer` 路径：高分向量命中直接依据首条证据回答，并只返回实际使用的唯一来源。

### 人工抽查

依据 `eval/answer_quality_rubric.md`，已人工标注 4/26 条样本：`rag_001`、`rag_006`、`rag_008`、`rag_015`。

| 指标 | 已标注结果 | 说明 |
| --- | --- | --- |
| Faithfulness | 4/4 = 1.0000 | 回答关键事实均能由来源支持 |
| Answer Relevance | 4/4 = 1.0000 | 回答直接处理用户问题 |
| Citation Correctness | 4/4 = 1.0000 | 回答正文与 API 来源一致 |

`rag_015` 曾暴露来源精确性问题：正文仅使用 `chunk-11` 的“超过 5000 元额外审批”规则，但 API 返回了重复且无关的流程父块。现已将高置信回答的 `sources` 收敛为首条实际用于回答的证据，普通 Agent 与 LangGraph 均已验证。

人工标注仍有 22 条待复核；因此当前结论是“自动检查覆盖 26/26，人工抽查 4/4 通过”，而不是声称全部样本均已人工确认。

## 可复现命令

```powershell
.\backend\.venv\Scripts\python.exe eval\run_rag_metrics_eval.py
.\backend\.venv\Scripts\python.exe eval\run_vector_rag_metrics_eval.py
.\backend\.venv\Scripts\python.exe eval\run_hybrid_rag_metrics_eval.py
.\backend\.venv\Scripts\python.exe eval\run_hybrid_reranked_metrics_eval.py
.\backend\.venv\Scripts\python.exe eval\run_answer_quality_auto_eval.py
.\backend\.venv\Scripts\python.exe eval\run_answer_quality_report.py
```

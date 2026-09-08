# RAG 生成侧人工评测标准

## 评测目标

评估 Agent 最终回答是否：

1. Faithfulness：回答中的关键事实能否从提供的来源中找到依据。
2. Answer Relevance：回答是否直接解决用户问题。
3. Citation Correctness：引用的来源是否确实支持回答。

## 评分规则

每项只打 `1` 或 `0`：

| 指标 | 1 分 | 0 分 |
| --- | --- | --- |
| Faithfulness | 所有关键事实均能被 sources 中的内容支持 | 存在来源没有提到的关键事实，或与来源矛盾 |
| Answer Relevance | 直接回答问题，且给出足够的可执行信息 | 跑题、只重复问题、缺少关键结论或步骤 |
| Citation Correctness | 每个引用都真实存在，且所引 chunk/父块支持回答 | 引用不存在、引用错文件/块，或引用不能支撑回答 |

## 判定示例

### 示例：出差费用怎么走流程

回答给出“登录 OA、上传发票和付款凭证、财务审核、审核通过后 3-5 个工作日打款”，并引用 `reimbursement_policy.md::parent-chunk-3`。

- Faithfulness：1。所有流程步骤都在父块内。
- Answer Relevance：1。完整回答了流程问题。
- Citation Correctness：1。父块就是这些步骤的来源。

### 示例：回答说“报销当天到账”

来源只写“审核通过后 3-5 个工作日打款”。

- Faithfulness：0。增加了来源不存在且矛盾的事实。
- Answer Relevance：可能为 1。它表面上回答了到账时间。
- Citation Correctness：0。引用无法支持“当天到账”。

## 人工标注原则

- 先看回答，再核对 `response.sources` 的 `snippet` 和 `chunk_id`。
- 只评价知识库回答，不评价工单创建或无关问题拦截。
- 不因语言润色普通就扣分；关键看事实、相关性和引用。
- 流程题若漏掉决定性步骤，Answer Relevance 记 0。

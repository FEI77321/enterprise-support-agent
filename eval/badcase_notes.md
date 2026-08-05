# Badcase Notes

## 背景

本项目当前是 Enterprise Support Agent 的第一版，使用本地 Markdown 知识库和关键词检索完成用户问题匹配。

评估脚本：

```powershell
backend\.venv\Scripts\python.exe eval\run_manual_eval.py

第一次评估
初始结果：
Passed: 6/8
失败样例：
case_002：怎么申请报销？
case_003：年假怎么申请？
问题原因
知识库检索中，每命中一个关键词加 3 分：
score += 3
当用户问题只命中一个关键词时，分数为 3。
早期 Agent 判断逻辑是：
if results and results[0].score >= 4:
因此单关键词命中的明确问题被误判为“不够确定”，系统转而创建工单。
第一次优化
将直接回答阈值从 4 调整为 3：
if results and results[0].score >= 3:
优化后，报销、年假等问题可以正常命中知识库。
第二次优化：增加 clarify 分支
为了让 Agent 更接近真实业务决策流，新增三段式判断：
score >= 6     -> 直接回答
0 < score < 6  -> 追问澄清
score == 0     -> 创建工单
新增返回类型：
type="clarify"
示例：
用户输入：我想报销
返回类型：clarify
第三次优化：补充关键词
由于阈值提升到 6 后，部分明确问题再次变成低置信匹配，例如：
怎么申请报销？
年假怎么申请？
因此补充更贴近用户表达的关键词：
"reimbursement_policy.md": ["报销", "申请报销", "怎么申请报销", "发票", "差旅", "费用", "打款", "审批"]
"leave_policy.md": ["请假", "年假", "年假申请", "怎么申请", "调休", "病假", "假期"]
最终评估目标：
Passed: 9/9
项目收获
这次优化体现了 Agent 应用开发中的一个基本闭环：
设计测试集 -> 运行评估 -> 发现 badcase -> 分析原因 -> 调整策略 -> 再次评估
```
## Cleanup Notes

- 修复 `models.py` 中 Pydantic 模型的缩进和格式问题，提升可读性。
- 统一接口层中文错误提示，保证 API 返回信息更清晰。
- 修复 `list_tickets` 中 `Ticket` 对象追加逻辑的缩进问题，避免 GET /tickets 返回空列表。
- 保持原有业务逻辑不变，并通过 `eval/run_manual_eval.py` 验证核心流程。
- 将知识库检索从整篇文档匹配升级为 chunk-level retrieval，并加入基于 query keyword 的轻量 reranking，使错误码类问题可以命中更精确的知识片段（720vpn）
- 将本地 Markdown 知识库检索从文档级关键词匹配升级为 chunk-level retrieval，设计 query-aware reranking 规则优先命中错误码等高置信片段，并在 API sources 中返回 chunk_id，实现可追溯的 RAG 引用与评估。


## Badcase: 中文短语未命中导致误创建工单

### 现象

用户输入：

```text
虚拟网卡驱动
知识库 vpn_guide.md 中实际存在相关内容：
4. 如果错误码为 720，请重装虚拟网卡驱动。
但系统没有返回知识库答案或追问，而是创建了新工单。
原因
第一版检索主要依赖手写关键词和简单的空格切词匹配。
由于中文短语没有天然空格，split() 无法正确切分：
"虚拟网卡驱动".split()
得到的仍然是一个整体字符串。
当文档 chunk 中包含标点和完整句子时，集合交集可能为空，导致相似度为 0。
优化
在关键词检索未命中时，增加 vector fallback 流程：
keyword retrieval -> vector fallback -> create ticket
当 fallback 检索到高于阈值的知识片段时，返回 clarify，并携带 file、snippet、score、chunk_id，避免直接误创建工单。
结果
输入：
虚拟网卡驱动
现在返回：
{
  "type": "clarify",
  "sources": [
    {
      "file": "vpn_guide.md",
      "chunk_id": "vpn_guide.md::chunk-6"
    }
  ],
  "ticket": null
}
系统能够定位到相关知识片段，并进入追问流程。

这个记录写完以后，第四阶段的“假 vector fallback”就闭环了：

```text
发现 badcase
-> 定位原因
-> 增加 fallback
-> 接入 /chat
-> 增加 eval
-> 记录 badcase
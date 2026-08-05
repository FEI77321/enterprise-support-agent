# Enterprise Support Agent 评测报告

本报告由 `eval/run_manual_eval.py` 自动生成，用于记录端到端 Agent 工作流评测结果。

## 评测结论

端到端评测结果：`Passed: 13/13`

结论：全部端到端 case 已通过，当前 Agent 主流程可以作为稳定版本继续迭代。

## 一键评测入口

如需同时运行配置评测、工具评测、LLM 质量评测、API smoke test 和端到端评测，执行：

```powershell
.\backend\.venv\Scripts\python.exe eval\run_all_eval.py
```

完整评测通过时，终端会输出：

```text
Config eval passed.
Tool eval: Passed 7/7
LLM quality eval: Passed 3/3
API smoke eval: Passed 4/4
Manual eval: Passed 13/13
Eval suites passed: 5/5
```

## 端到端评测范围

端到端评测直接调用 `handle_message()`，覆盖用户消息进入 Agent 后的完整处理流程：

- 用户输入解析
- 工单号提取
- Markdown 知识库检索
- ChromaDB 向量检索 fallback
- 低置信度澄清追问
- 自动创建工单
- 工单状态查询
- LLM Stub 分支
- `workflow_steps` 执行轨迹记录

## Case 汇总

| Case | 状态 | 输入 | 期望检查 | 创建工单 |
| --- | --- | --- | --- | --- |
| case_001 | PASS | VPN 连不上怎么办？ | response_type=answer; source=vpn_guide.md; workflow contains: extract_ticket_id -> search_knowledge_base -> knowledge_answer | 否 |
| case_002 | PASS | 怎么申请报销？ | response_type=answer; source=reimbursement_policy.md | 否 |
| case_003 | PASS | 年假怎么申请？ | response_type=answer; source=leave_policy.md | 否 |
| case_004 | PASS | 账号登录不了怎么办？ | response_type=answer; source=account_login_faq.md | 否 |
| case_005 | PASS | 我的电脑蓝屏了，开不了机 | response_type=ticket_created; priority=HIGH | 是 |
| case_006 | PASS | 打印机一直卡纸，没人会修 | response_type=ticket_created; priority=MEDIUM | 是 |
| case_007 | PASS | 显示器突然黑屏，影响办公 | response_type=ticket_created; priority=MEDIUM | 是 |
| case_008 | PASS | 远程办公连不上公司内网 | response_type=answer; source=vpn_guide.md | 否 |
| case_009 | PASS | 我想报销 | response_type=clarify | 否 |
| case_010 | PASS | VPN 720 错误怎么办 | response_type=answer; source=vpn_guide.md; chunk_id=vpn_guide.md::chunk-6 | 否 |
| case_011 | PASS | 虚拟网卡驱动 | response_type=clarify; source=vpn_guide.md; chunk_id=vpn_guide.md::chunk-6; workflow contains: search_knowledge_base -> search_vector_store -> vector_clarify | 否 |
| case_012 | PASS | 帮我查一下 TICKET-20990101-9999 | response_type=ticket_status; workflow contains: extract_ticket_id -> query_ticket_status -> ticket_not_found; answer contains: 没有找到工单 | 否 |
| case_013 | PASS | VPN 720 错误怎么办 | response_type=answer; workflow contains: rule_answer -> llm_answer -> knowledge_answer | 否 |

## Workflow 验证

评测不仅检查最终响应类型，还会检查 `workflow_steps`，确保 Agent 的内部执行路径符合预期。

典型路径示例：

```text
知识库直接回答:
extract_ticket_id -> search_knowledge_base -> rule_answer -> knowledge_answer

向量检索追问:
extract_ticket_id -> search_knowledge_base -> search_vector_store -> vector_clarify

创建工单:
extract_ticket_id -> search_knowledge_base -> search_vector_store -> create_ticket -> ticket_created

查询不存在工单:
extract_ticket_id -> query_ticket_status -> ticket_not_found

LLM Stub 回答:
extract_ticket_id -> search_knowledge_base -> rule_answer -> llm_answer -> knowledge_answer
```

## 详细结果

### case_001 PASS

- Input: VPN 连不上怎么办？
- Expected: {"response_type": "answer", "source": "vpn_guide.md", "workflow_contains": ["extract_ticket_id", "search_knowledge_base", "knowledge_answer"]}
- Env: {}
- Actual: type=answer, sources=[{'file': 'vpn_guide.md', 'score': 6, 'chunk_id': 'vpn_guide.md::chunk-2'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'knowledge_answer']
- Ticket created: False

### case_002 PASS

- Input: 怎么申请报销？
- Expected: {"response_type": "answer", "source": "reimbursement_policy.md"}
- Env: {}
- Actual: type=answer, sources=[{'file': 'reimbursement_policy.md', 'score': 9, 'chunk_id': 'reimbursement_policy.md::chunk-2'}, {'file': 'leave_policy.md', 'score': 3, 'chunk_id': 'leave_policy.md::chunk-2'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'knowledge_answer']
- Ticket created: False

### case_003 PASS

- Input: 年假怎么申请？
- Expected: {"response_type": "answer", "source": "leave_policy.md"}
- Env: {}
- Actual: type=answer, sources=[{'file': 'leave_policy.md', 'score': 6, 'chunk_id': 'leave_policy.md::chunk-3'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'knowledge_answer']
- Ticket created: False

### case_004 PASS

- Input: 账号登录不了怎么办？
- Expected: {"response_type": "answer", "source": "account_login_faq.md"}
- Env: {}
- Actual: type=answer, sources=[{'file': 'account_login_faq.md', 'score': 6, 'chunk_id': 'account_login_faq.md::chunk-2'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'knowledge_answer']
- Ticket created: False

### case_005 PASS

- Input: 我的电脑蓝屏了，开不了机
- Expected: {"response_type": "ticket_created", "priority": "HIGH"}
- Env: {}
- Actual: type=ticket_created, sources=[], ticket_id=TICKET-20260805-0382,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'search_vector_store', 'create_ticket', 'ticket_created']
- Ticket created: True

### case_006 PASS

- Input: 打印机一直卡纸，没人会修
- Expected: {"response_type": "ticket_created", "priority": "MEDIUM"}
- Env: {}
- Actual: type=ticket_created, sources=[], ticket_id=TICKET-20260805-0383,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'search_vector_store', 'create_ticket', 'ticket_created']
- Ticket created: True

### case_007 PASS

- Input: 显示器突然黑屏，影响办公
- Expected: {"response_type": "ticket_created", "priority": "MEDIUM"}
- Env: {}
- Actual: type=ticket_created, sources=[], ticket_id=TICKET-20260805-0384,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'search_vector_store', 'create_ticket', 'ticket_created']
- Ticket created: True

### case_008 PASS

- Input: 远程办公连不上公司内网
- Expected: {"response_type": "answer", "source": "vpn_guide.md", "note": "当前关键词检索可能搜不到，这是后续升级 RAG 的 badcase"}
- Env: {}
- Actual: type=answer, sources=[{'file': 'vpn_guide.md', 'score': 9, 'chunk_id': 'vpn_guide.md::chunk-2'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'knowledge_answer']
- Ticket created: False

### case_009 PASS

- Input: 我想报销
- Expected: {"response_type": "clarify"}
- Env: {}
- Actual: type=clarify, sources=[{'file': 'reimbursement_policy.md', 'score': 3, 'chunk_id': 'reimbursement_policy.md::chunk-2'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'clarify']
- Ticket created: False

### case_010 PASS

- Input: VPN 720 错误怎么办
- Expected: {"response_type": "answer", "source": "vpn_guide.md", "chunk_id": "vpn_guide.md::chunk-6"}
- Env: {}
- Actual: type=answer, sources=[{'file': 'vpn_guide.md', 'score': 6, 'chunk_id': 'vpn_guide.md::chunk-6'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'knowledge_answer']
- Ticket created: False

### case_011 PASS

- Input: 虚拟网卡驱动
- Expected: {"response_type": "clarify", "source": "vpn_guide.md", "chunk_id": "vpn_guide.md::chunk-6", "workflow_contains": ["search_knowledge_base", "search_vector_store", "vector_clarify"]}
- Env: {}
- Actual: type=clarify, sources=[{'file': 'vpn_guide.md', 'score': 200, 'chunk_id': 'vpn_guide.md::chunk-6'}, {'file': 'reimbursement_policy.md', 'score': 58, 'chunk_id': 'reimbursement_policy.md::chunk-3'}, {'file': 'reimbursement_policy.md', 'score': 31, 'chunk_id': 'reimbursement_policy.md::chunk-2'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'search_vector_store', 'vector_clarify']
- Ticket created: False

### case_012 PASS

- Input: 帮我查一下 TICKET-20990101-9999
- Expected: {"response_type": "ticket_status", "answer_contains": "没有找到工单", "workflow_contains": ["extract_ticket_id", "query_ticket_status", "ticket_not_found"]}
- Env: {}
- Actual: type=ticket_status, sources=[], ticket_id=None,workflow_steps=['extract_ticket_id', 'query_ticket_status', 'ticket_not_found']
- Ticket created: False

### case_013 PASS

- Input: VPN 720 错误怎么办
- Expected: {"response_type": "answer", "workflow_contains": ["rule_answer", "llm_answer", "knowledge_answer"]}
- Env: {"ENABLE_LLM_ANSWER": "true", "LLM_PROVIDER": "stub"}
- Actual: type=answer, sources=[{'file': 'vpn_guide.md', 'score': 6, 'chunk_id': 'vpn_guide.md::chunk-6'}], ticket_id=None,workflow_steps=['extract_ticket_id', 'search_knowledge_base', 'rule_answer', 'llm_answer', 'llm_invalid_citation_fallback', 'knowledge_answer']
- Ticket created: False

## 面试讲法

```text
我没有只做功能演示，而是把评测分成配置评测、工具评测、LLM 质量评测、API smoke test 和端到端评测五层。
端到端评测会直接调用 Agent 的 handle_message()，检查响应类型、知识库来源、chunk_id、工单优先级和 workflow_steps。
LLM 质量评测会验证开启 LLM Stub 后是否进入 llm_answer 分支，同时保留 sources 和正确 workflow；也会验证 OpenAI provider 缺少 API Key 时的 fallback，以及 mock OpenAI SDK 调用链路。
API smoke test 会通过 FastAPI TestClient 验证 /health、/version、/chat 正常响应和参数校验，确认 HTTP 接口层没有退化。
这样每次改动后都可以通过 run_all_eval.py 一键回归，确认配置层、工具层、LLM 链路、HTTP 接口层和 Agent 工作流都没有退化。
```

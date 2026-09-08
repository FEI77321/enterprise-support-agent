# Enterprise Support Agent 简历与面试包装

本文档用于把当前阶段的 Enterprise Support Agent 项目整理成简历描述和面试表达。当前阶段重点不是“炫模型”，而是展示一个 AI Agent 应用从功能、工具、检索、配置到评测的工程化能力。

## 简历项目名称

Enterprise Support Agent：企业内部 IT 支持智能体

## 一句话项目描述

基于 FastAPI、Pydantic、本地 Markdown 知识库、ChromaDB 向量检索和 Tool Registry，实现一个面向企业 IT 支持场景的 AI Agent，支持知识库问答、澄清追问、工单创建、工单查询、LLM Stub/OpenAI 可配置接入和多层评测回归。

## 简历 Bullet 版本

可以放在简历项目经历里：

- 设计并实现企业 IT 支持 Agent，覆盖 VPN 故障、账号登录、报销、请假、办公设备故障和工单查询等典型企业内部支持场景。
- 使用 FastAPI + Pydantic 构建后端接口和响应模型，拆分 `/chat`、`/tickets`、`/health`、`/version` 等接口，保证请求响应结构清晰可维护。
- 构建基于本地 Markdown 文档的知识库检索能力，支持 chunk-level retrieval，并在响应中返回 `file`、`score`、`chunk_id` 等可解释来源信息。
- 引入 ChromaDB 本地向量检索作为 RAG fallback，并结合 exact match 和 rerank 处理中文短 query、错误码和专有名词召回不稳定问题。
- 抽象 Tool Registry，统一管理 `query_ticket_status`、`create_ticket`、`search_knowledge_base`、`search_vector_store` 等工具调用，并处理 unknown tool、异常和工具执行日志。
- 使用 AgentState 管理单次请求上下文，通过 `workflow_steps` 记录 Agent 决策轨迹，提升流程可解释性和调试效率。
- 封装可配置 LLM Client，支持 `stub` 和 `openai` provider，通过环境变量控制是否启用 LLM 回答，并提供 fallback 保证主流程稳定。
- 设计配置评测、工具评测、LLM 质量评测和端到端评测四层回归体系，覆盖 7 个工具测试、3 个 LLM 链路测试和 13 个端到端 case，并提供 `run_all_eval.py` 一键运行全部评测。
- 补充 `.env.example`、`.gitignore`、README 和评测报告，规范密钥管理、运行说明和项目交付文档。

## P2 工程化补充（可替换或追加到简历）

- 为 FastAPI 请求接入 `X-Request-ID` 全链路追踪，统一 HTTP 响应头、结构化日志、Agent 状态和聊天响应中的请求标识，便于定位限流、重试与流式中断问题。
- 使用 Redis Lua 脚本实现按客户端 IP 的固定窗口分布式限流，仅保护 `/chat` 与 `/chat/stream`；通过 `429`、`Retry-After` 及额度响应头向前端提供可恢复的反馈。
- 抽象 OpenAI/DeepSeek 的统一重试层：仅对超时、连接异常、429 和 5xx 进行有限指数退避重试，4xx 快速失败，最终沿用规则答案/无工具调用的安全降级。
- 新增 `POST /chat/stream` SSE 接口和 React `fetch + ReadableStream` 消费端，推送处理状态、回答分片、工作流和最终结构化结果；当前为阶段事件与完成答案分片流，未宣称模型原生 token 流。
- 新增 P2 聚合回归 `eval/run_p2_engineering_eval.py`，离线覆盖 Redis 配置、限流、LLM 重试、Trace/API、SSE 和 LangGraph 行为一致性。

## 简历短版

如果简历空间不够，可以压缩成 4 条：

- 基于 FastAPI + Pydantic 实现企业 IT 支持 Agent，支持知识库问答、澄清追问、工单创建和工单查询。
- 构建 Markdown 知识库检索 + ChromaDB 向量检索 fallback，并返回 source、score、chunk_id 提升回答可解释性。
- 设计 Tool Registry 和 AgentState，统一工具调用、异常处理和 `workflow_steps` 执行轨迹记录。
- 搭建配置评测、工具评测、LLM 质量评测、端到端评测四层回归体系，当前通过 `Tool eval 7/7`、`LLM quality eval 3/3`、`Manual eval 13/13`、`Eval suites 4/4`。

## 面试 1 分钟介绍

我做了一个企业内部 IT 支持 Agent，主要解决员工在 VPN、账号登录、报销、请假、办公设备故障等场景下的咨询和工单处理问题。

用户输入后，Agent 会先判断是否包含工单号，如果有就查询工单状态；如果没有，就先检索本地 Markdown 知识库。高置信命中时直接返回答案和来源，低置信命中时追问用户补充信息。如果关键词检索不够，会进入 ChromaDB 向量检索 fallback；仍然无法解决时，会自动创建 IT 支持工单。

工程上我做了 Tool Registry 来统一管理工具调用，用 AgentState 保存请求上下文，并通过 workflow_steps 记录 Agent 的执行路径。LLM 部分做成可配置的 stub/openai provider，默认使用 stub 保证评测稳定，并新增 LLM 质量评测验证 `llm_answer` 链路。最后我搭了配置评测、工具评测、LLM 质量评测和端到端评测四层回归，目前一键评测是 4/4 通过。

## 面试 3 分钟介绍

这个项目的背景是企业内部 IT 支持场景。传统客服系统通常是 FAQ 搜索或者人工建单，我想把它做成一个小型 AI Agent：既能回答明确问题，也能在信息不足时追问，还能在无法解决时创建工单。

整体架构分成几层。第一层是 FastAPI 接口层，提供 `/chat` 和 `/tickets` 等接口；第二层是 Agent 工作流层，核心入口是 `handle_message()`；第三层是工具层，通过 Tool Registry 统一注册和调用工具；第四层是知识检索层，包括 Markdown 关键词检索和 ChromaDB 向量检索；第五层是 LLM Client，支持 stub 和 OpenAI provider。

一个典型请求进来后，Agent 会先创建 AgentState，然后提取工单号。如果用户输入里有工单号，就调用 `query_ticket_status`。如果没有工单号，就调用 `search_knowledge_base`。高置信命中时，返回知识库答案，并带上 source 和 chunk_id；低置信时，返回 clarify 让用户补充信息。如果关键词检索召回不够，则调用 `search_vector_store` 做向量检索 fallback。最后如果仍然无法处理，就调用 `create_ticket` 创建工单。

我比较重视可解释性，所以每个响应都会带 `workflow_steps`。比如知识库回答路径可能是 `extract_ticket_id -> search_knowledge_base -> rule_answer -> knowledge_answer`，创建工单路径可能是 `extract_ticket_id -> search_knowledge_base -> search_vector_store -> create_ticket -> ticket_created`。这样不仅方便调试，也方便面试时讲清楚 Agent 内部到底做了什么。

LLM 部分我没有一开始就强依赖真实模型，而是做了配置开关。默认 `LLM_PROVIDER=stub`，保证本地 eval 稳定；配置 OpenAI 或 DeepSeek 后可走真实模型调用。同时如果没有 key 或调用最终失败，会回退到规则答案；对超时、连接异常、429 与 5xx 会做有限指数退避重试。

最后是评测体系。我把评测拆成四层：配置评测验证环境变量解析；工具评测验证每个工具能独立运行；LLM 质量评测验证开启 LLM Stub 后是否进入 `llm_answer` 分支并保留 sources，同时验证 OpenAI provider 缺少 API Key 时可以安全 fallback，并用 mock client 验证真实 SDK 调用参数；端到端评测验证完整 Agent 工作流。目前工具评测 7/7、LLM 质量评测 3/3、端到端 case 13/13，并且用 `run_all_eval.py` 一键运行全部评测。这是这个项目从 demo 走向工程化的关键。

## 当前阶段亮点

### 1. Agent 不是单轮问答，而是有决策流

项目不是简单把用户问题丢给模型，而是先做流程判断：

```text
是否包含工单号
-> 是否命中知识库
-> 是否需要澄清
-> 是否需要向量检索
-> 是否需要创建工单
```

这体现的是 Agent workflow 设计能力。

### 2. 工具调用有统一抽象

通过 `tool_registry.py` 统一管理工具：

```text
query_ticket_status
create_ticket
search_knowledge_base
search_vector_store
```

好处是后续接真实 Tool Calling、LangGraph 或更多企业系统时，不需要重写主流程。

### 3. RAG 检索做了多层召回

当前检索不是单纯关键词匹配，而是：

```text
Keyword Retrieval
-> ChromaDB Vector Retrieval
-> Exact Match
-> Rerank
```

这个设计是为了解决中文短 query、错误码、专有名词在向量检索里不稳定的问题。

### 4. workflow_steps 增强可解释性

每次响应都会记录 Agent 执行路径，既方便 debug，也方便面试讲解。例如：

```text
extract_ticket_id -> search_knowledge_base -> rule_answer -> knowledge_answer
```

### 5. LLM 接入是可配置的

通过环境变量控制：

```text
ENABLE_LLM_ANSWER=false
LLM_PROVIDER=stub
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5
```

这样可以保证：

- 没有 API Key 时项目也能跑。
- eval 不依赖真实模型输出。
- 需要真实模型时可以切换到 OpenAI。

### 6. 有回归评测，不只是功能演示

当前评测结果：

```text
Config eval passed.
Tool eval: Passed 7/7
LLM quality eval: Passed 3/3
Manual eval: Passed 13/13
Eval suites passed: 4/4
```

这说明项目具备持续迭代的基础。

## 常见面试追问

### Q1：为什么不直接把所有问题都发给大模型？

因为企业支持场景里，很多问题有明确流程和内部知识来源。直接发给大模型容易出现两个问题：一是答案不可控，二是可能编造。  
所以我先用知识库和规则流程保证稳定性，再把 LLM 放在可配置增强层，用来优化表达，而不是让它直接决定所有业务逻辑。

### Q2：为什么要有 stub provider？

stub 的作用是保证 eval 稳定。真实 LLM 输出有随机性，也可能因为网络、额度或 API Key 问题失败。如果评测强依赖真实模型，项目就很难稳定回归。  
所以我默认使用 stub，真实 OpenAI 调用通过环境变量开启。

### Q3：workflow_steps 有什么用？

它是 Agent 的执行轨迹。  
用户只看到最终答案，但开发者需要知道 Agent 到底走了哪条路径：是知识库回答、向量检索追问、创建工单，还是查询工单。  
这对 debug、评测和面试讲解都很重要。

### Q4：为什么要做 Tool Registry？

Tool Registry 可以把工具调用从 Agent 主逻辑里抽离出来。  
Agent 只需要通过工具名调用工具，不需要关心每个工具内部怎么实现。后续如果接数据库、企业 IM、工单系统或真实 Tool Calling，这个结构更容易扩展。

### Q5：为什么要返回 source 和 chunk_id？

这是为了可解释性。  
企业知识库问答不能只给答案，还要知道答案来自哪个文档、哪个片段。`source` 和 `chunk_id` 可以帮助用户或开发者追溯答案来源，也方便评测检查召回是否正确。

### Q6：为什么既有关键词检索，又有向量检索？

关键词检索适合错误码、产品名、流程名等明确词；向量检索适合语义相近但表达不同的问题。  
两者结合可以提高召回稳定性。项目里还加了 exact match 和 rerank，是为了增强中文短 query 和专有名词场景下的命中效果。

### Q7：你现在接入真实大模型了吗？

当前已经完成 LLM Client 的工程化封装，支持 `stub` 和 `openai` provider，并通过环境变量控制是否启用。  
默认使用 stub 保证评测稳定；配置 `LLM_PROVIDER=openai` 和 `OPENAI_API_KEY` 后，就可以走真实 OpenAI 调用。下一阶段会进一步完善 OpenAI 调用参数、超时控制和输出质量评测。

### Q8：这个项目和普通 RAG Demo 的区别是什么？

普通 RAG Demo 往往只做“检索 + 回答”。  
这个项目除了 RAG，还加入了 Agent 决策流、Tool Registry、工单 action、workflow trace、环境变量配置、fallback 和多层 eval，更接近一个可迭代的 Agent 应用工程。

## 项目当前阶段总结

当前阶段已经完成：

- 后端 API 基础能力
- 本地知识库问答
- ChromaDB 向量检索 fallback
- 工单创建和查询
- Tool Registry
- AgentState
- workflow_steps
- LLM Stub/OpenAI 可配置入口
- `.env.example` 和 `.gitignore` 安全配置
- README 和 eval_report 项目文档
- `run_all_eval.py` 一键评测
- 配置评测、工具评测、端到端评测

当前阶段可以定位为：

```text
一个具备工程化基础的企业支持 Agent 原型。
```

下一阶段可以进入：

```text
真实 OpenAI 调用增强 + LLM 输出质量评测 + API smoke test + 前端页面。
```

## 下一阶段路线

建议按照这个顺序推进：

1. 完善真实 OpenAI 调用：增加 timeout、日志、fallback 和更清晰的错误处理。
2. 增加 LLM 输出质量评测：检查回答是否引用 sources、是否拒绝编造、是否覆盖关键步骤。
3. 增加 API smoke test：验证 `/health`、`/version`、`/chat` 真实 HTTP 接口可用。
4. 增加简单前端页面：展示聊天、sources、workflow_steps 和工单信息。
5. 将手写 eval 逐步迁移到 pytest，增强测试规范性。

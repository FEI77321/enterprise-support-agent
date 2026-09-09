# Agent Harness 面试题卡（已实现版）

## 1. 你在项目中实现的 Harness 做了什么？

我新增了轻量 AgentHarness 作为统一工具执行层。rules Agent、LangGraph 和 Tool Calling 在真正执行工具前都会经过它；它做工具注册和参数校验、风险分级、删除确认、请求级 max_steps、步骤 Trace 和错误分类。LangGraph 仍然只负责编排业务图，Tool Registry 仍然负责真实工具分派。

## 2. 为什么 LangGraph 不能替代 Harness？

LangGraph 解决业务流程的节点和条件边；Harness 解决所有调用路径共有的运行时问题，例如某工具能否执行、是否高风险、已执行几步、如何记录 Trace、异常如何结束。若只在 Graph 内处理，Tool Calling 或新入口容易绕过规则。

## 3. 删除确认如何保证不绕过？

删除工具属于 `write_high_risk`。首次请求进入 Harness 后只返回 `confirmation_required`，并保存 session 绑定的 pending 操作；用户确认时仍然通过 Harness 的 `confirmed=True` 路径执行，因此参数校验、Trace 和步数控制不会被绕过。

## 4. max_steps 如何工作？

每个请求有一个 HarnessSession，保存最大步数和已执行步数。真实工具调用前检查上限；达到上限时记录 `max_steps_exceeded` 并停止，不调用 handler。当前默认上限为 4，可通过环境变量调整。

## 5. 如何观测一次工具执行？

HarnessTraceStep 关联 request_id，记录工具名、风险等级、参数摘要、状态、耗时与错误类型。业务路径仍由 workflow_steps 表示；前者用于执行级诊断，后者用于解释业务路由。当前是请求级 Trace，不是持久化回放平台。

## 6. 还有哪些没有做？

没有做 Context Manager、长期记忆恢复、Trace 数据库和前端回放、通用工具 timeout/retry、RBAC、多 Agent 或 Sandbox。这些需要真实长任务、身份系统、幂等和故障数据，当前不为了堆概念过度工程。

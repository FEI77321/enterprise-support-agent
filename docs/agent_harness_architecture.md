# Agent Harness 运行时治理升级

## 已实现范围

项目新增 `backend/app/agent_harness.py`，将工具执行治理收敛为 `AgentHarness.execute_tool()`。它不替代 LangGraph 的业务图，也不替代 Tool Registry 的工具实现；只负责每次真实工具调用前后的运行时控制。

```text
rules Agent / LangGraph / Tool Calling
                ↓
       AgentHarness.execute_tool()
  白名单与参数校验 / 风险等级 / 确认策略
  max_steps / 请求级 Trace / 工具错误分类
                ↓
         Tool Registry → 真实工具
```

## 三条接入路径

- **rules Agent**：`agent.py` 的查询工单、关键词检索、向量检索、创建工单通过 `_run_rules_tool()` 进入 Harness；这是默认聊天主链路。
- **LangGraph**：`graph_agent.py` 的对应节点通过 `_run_graph_tool()` 进入 Harness，业务节点和条件边保持不变。
- **Tool Calling**：`tool_call_executor.py` 通过 Harness 运行已解析工具调用；用户确认删除后，`tool_call_agent.py` 以 `confirmed=True` 再次经过同一入口执行，避免确认后的真实删除绕过 Trace 与参数校验。

## 安全与运行时策略

`ToolActionPolicy` 现在同时表达确认需求和最小风险等级：

| 工具 | 风险等级 | 策略 |
|---|---|---|
| 查询工单、知识库/向量检索 | `read_only` | 直接执行 |
| 创建工单 | `write_low_risk` | 直接执行并保留 Trace |
| 删除工单 | `write_high_risk` | 先保存 pending confirmation，确认后执行 |

Harness 在真实执行前依次检查：步骤上限、工具注册、参数绑定、确认策略。未知工具、参数非法、未确认删除、步数超限均不会调用真实 handler。

## 请求级 Trace

每个 Trace Step 记录：步骤号、工具名、风险等级、参数摘要、状态、耗时、错误类型。状态包括：`completed`、`confirmation_required`、`blocked`、`failed`、`max_steps_exceeded`。

`ChatResponse.harness_trace` 会在 rules / LangGraph Harness 开启时返回这份请求级轨迹；关闭开关时为空。参数只保留 80 字符以内的摘要，不默认记录长文本或完整知识库内容。

## Feature Flag 与边界

```env
AGENT_HARNESS_ENABLED=true
AGENT_HARNESS_MAX_STEPS=4
```

将 `AGENT_HARNESS_ENABLED=false` 可回退至改造前的工具执行路径；关闭时不创建 Harness Session 或 Trace。

本次不实现：上下文摘要、跨请求任务恢复、Trace 持久化与回放、通用工具 timeout/retry、RBAC、多 Agent、Sandbox、前端 Trace 时间线。LLM 的有限重试、RAG fallback 和 Redis 限流仍由既有模块负责。

## 验证证据

`eval/run_agent_harness_contract_eval.py` 覆盖：风险等级、未知工具、非法参数、高风险确认、步数上限、rules 主链路 Trace、LangGraph 主链路 Trace、Feature Flag 回退，共 8 项契约。

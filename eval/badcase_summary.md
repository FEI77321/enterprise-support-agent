# Badcase 修复记录

## 2026-07-27：知识库匹配阈值问题

### 失败用例

- case_002：怎么申请报销？
- case_003：年假怎么申请？

### 问题现象

自动评估脚本运行结果为：

```text
Passed: 6/8
原因分析
在 knowledge_base.py 中，每命中一个关键词会加 3 分：
if keyword.lower() in query.lower():
    score += 3
但是在 agent.py 中，只有当最高匹配分数大于等于 4 时，系统才认为知识库命中足够明确：
if results and results[0].score >= 4:
所以用户问：
怎么申请报销？
只命中了一个关键词：
报销
最终得分是 3。
因为：
3 < 4
所以系统没有返回知识库答案，而是误判为需要创建工单。
修复方式
将 agent.py 中的知识库回答阈值从 4 调整为 3：
if results and results[0].score >= 3:
修复结果
重新运行评估脚本：
backend\.venv\Scripts\python.exe eval\run_manual_eval.py
结果变为：
Passed: 8/8
说明本次 badcase 修复成功。
本次收获
这一步完成了一个真实 Agent 项目里的评估闭环：
发现 badcase
-> 定位原因
-> 调整策略
-> 重新评估
-> 记录结果

 if priority is not None and ticket_data["priority"] != priority:
            continue
            ticket=Ticket(**ticket_data)
            tickets.append(ticket)
缩进在 continue 后面，永远执行不到。
因为一旦执行 continue，循环直接进入下一轮，下面代码不会跑。
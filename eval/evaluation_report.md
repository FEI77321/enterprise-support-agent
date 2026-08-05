# Evaluation Report

## 评估目标

本次评估用于验证 Enterprise Support Agent 第一版规则系统的核心能力，包括：

- 企业知识库问题识别
- 本地文档检索结果是否正确
- 工单创建逻辑是否触发
- 工单优先级判断是否符合预期

## 评估方式

当前版本使用人工编写的测试集：

```text
eval/test_cases.json
并通过自动评估脚本运行：
backend\.venv\Scripts\python.exe eval\run_manual_eval.py
评估脚本会检查：
response.type 是否符合预期
知识库问题是否返回正确的 source
工单问题是否生成正确的 priority
测试结果
PASS case_001: VPN 连不上怎么办？
PASS case_002: 怎么申请报销？
PASS case_003: 年假怎么申请？
PASS case_004: 账号登录不了怎么办？
PASS case_005: 我的电脑蓝屏了，开不了机
PASS case_006: 打印机一直卡纸，没人会修
PASS case_007: 显示器突然黑屏，影响办公
PASS case_008: 远程办公连不上公司内网

Passed: 8/8
当前覆盖范围
本次测试集覆盖了 3 类核心场景：
知识库问答
VPN 问题
报销问题
年假问题
账号登录问题

工单创建
电脑蓝屏
打印机卡纸
显示器黑屏

模糊知识库问题
远程办公无法连接公司内网

当前结论
第一版规则 Agent 已经能够完成基础企业支持场景：
对明确知识库问题返回答案和来源文档
对无法直接回答的问题创建工单
对部分故障问题判断优先级
通过自动评估脚本完成基础回归验证
当前局限
当前系统仍然是规则版 MVP，存在以下限制：
依赖关键词匹配，无法理解复杂语义
知识库匹配阈值需要人工调整
测试集数量较少，目前只有 8 条
还没有 RAG、Embedding、向量数据库
还没有 LLM 生成式回答和 Tool Calling
后续计划
后续版本会继续升级：
扩展测试集到 30-50 条
增加 badcase 分类统计
引入 ChromaDB / LlamaIndex 实现 RAG
增加 Tool Calling 工具封装
增加 Agent trace 和日志分析
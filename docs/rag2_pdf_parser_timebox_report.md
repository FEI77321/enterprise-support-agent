# Day 6：复杂 PDF 解析时间盒对照

## 结论

本轮**不将 MinerU 接入 Enterprise Support Agent 的运行链路**。现有 `pypdf` 基线已经满足当前秋招收缩版的 P0 目标：文本型 PDF 可以解析、保留页码、进入版本化摄入与来源回链；复杂表格的结构丢失是已知且被记录的边界。

停止本地 MinerU 集成的依据不是“没有尝试”，而是环境与投入产出比不匹配：项目当前虚拟环境为 Windows + Python 3.13，而 MinerU 官方 README 说明 Windows 本地部署受 `ray` 依赖限制，仅支持 Python 3.10—3.12；官方完整安装还需要 `mineru[all]`、模型与较大的本地磁盘空间。为单次 synthetic 表格对照新建 Python 3.12 环境、安装大依赖和下载模型，会超过本项目 Day 6 的两小时上限，并引入与现有 `torch` / Python 环境的兼容风险。

官方依据：

- [MinerU README：Windows Python 版本与资源要求](https://github.com/opendatalab/MinerU/blob/master/README.md)
- [MinerU pyproject：`mineru[all]` 的依赖组成](https://github.com/opendatalab/MinerU/blob/master/pyproject.toml)

## 测试对象与方法

使用 synthetic 语料中两份单页表格 PDF：

| 文件 | 文档类型 | 关注点 |
| --- | --- | --- |
| `expense_approval_matrix.pdf` | 费用审批表 | 金额区间、审批人、补充材料的文本提取与表格结构 |
| `network_change_window_calendar.pdf` | 网络变更窗口表 | 时间窗口、审批要求、回退要求的文本提取与表格结构 |

运行脚本：

```powershell
.\backend\.venv\Scripts\python.exe .\eval\run_pdf_parser_baseline_eval.py
```

脚本对每份 PDF 使用当前 `PdfTextDocumentParser` 连续解析 5 次，验证：

1. `ParseStatus.SUCCESS`；
2. 页码映射存在且为第 1 页；
3. 5 个预设业务事实锚点均能从解析文本中找到；
4. 输出中没有真实 Markdown 表格行（至少两条 `|` 的行），以证明基础解析没有错误地宣称保留了行列结构；
5. 输出平均、最小、最大解析耗时。

## 基线结果

在本机项目虚拟环境（`pypdf 5.9.0`、Windows、Python 3.13）中的一次实测：

| 文件 | 解析状态 | 页码 | 事实锚点 | Markdown 表格结构 | 5 次平均耗时 |
| --- | --- | ---: | --- | --- | ---: |
| `expense_approval_matrix.pdf` | success | 1 | 5/5 | 否 | 4.673 ms |
| `network_change_window_calendar.pdf` | success | 1 | 5/5 | 否 | 3.661 ms |

解释：`pypdf` 能抽出表格中的文字，因此金额、审批人、窗口时间等事实仍可用于基础检索；但单元格被展平成阅读顺序文本，缺少可靠的“第几行、第几列、表头到单元格对应关系”。解析文本中的单个 `|` 仅来自文档元信息行，不是 Markdown 表格。

## MinerU 候选能力与本次取舍

MinerU 的价值在于版面分析、表格结构、公式、OCR 与 Markdown / JSON 转换；这正好能改善本基线“有文字、无行列结构”的缺口。

但本项目当前不接入，原因如下：

| 维度 | 基线 `pypdf` | MinerU 本地集成 | 本轮决策 |
| --- | --- | --- | --- |
| 文本型 PDF | 可解析并保留页码 | 可解析 | 基线满足 P0 |
| 表格事实锚点 | 可检索 | 预计可检索且更结构化 | 当前 fixture 已有 5/5 事实覆盖 |
| 表格行列关系 | 不保留 | MinerU 的主要收益 | 记录为明确缺口，不为它重构链路 |
| 扫描件 OCR | 不支持，失败隔离 | 可支持 | 目前 `FAILED + 无 Chunk` 更安全 |
| Windows + Python 3.13 | 当前可运行 | 官方说明 Windows 仅 3.10—3.12 | 不污染项目 venv |
| 本地成本 | 约 3—5 ms / 单页 fixture | 需要独立环境、依赖和模型 | 超出 Day 6 时间盒 |

## 面试表达

> 我用两份 synthetic 表格 PDF 对基础 `pypdf` 解析做了 5 次基线测量。它能稳定抽取审批金额、审批人、时间窗口等事实，并保留页码，单页解析约 3—5ms；但无法保留可靠的表格行列关系。MinerU 能补版面、表格和 OCR，但本机是 Windows + Python 3.13，而官方 Windows 本地部署限制在 Python 3.10—3.12，且完整本地方案还涉及模型与较大依赖。考虑到当前项目的目标是秋招可讲闭环，我把 MinerU 定位为明确记录的后续演进方案，而不是为了技术栈把它强接进主链路。扫描件当前会失败隔离、不会产生 Chunk，因此不会污染检索。

## 后续触发条件

只有满足以下任一条件，才重新评估 MinerU：

1. 面试或真实使用场景明确要求表格行列级问答；
2. 可使用独立 Python 3.12 环境，且不污染项目运行环境；
3. 有至少 5 份真实授权复杂 PDF，能定义结构保真、页码、耗时和检索收益的评测口径；
4. 接入后仍能保持现有失败隔离、版本管理与 feature flag 回退机制。

在上述条件不具备前，维持 `pypdf + 失败隔离 + 页码回链` 是当前项目更合适的工程选择。

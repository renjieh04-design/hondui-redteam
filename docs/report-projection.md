# RPT-01 报告投影与统计口径

`redteam.reporting.projection.project_run(records)` 接收已持久化的
`TaskRunRecords`，返回 JSON、JSONL 和 Markdown 可共用的 `ReportProjection`。
投影按任务、测试项、用例和步骤组织数据。
步骤下列出逻辑调用、每次尝试、历次评估和证据引用。
被测应用只投影名称、描述、适配器类型和模型名。
请求与响应正文通过已有证据引用追溯。

## 调研依据

Inspect AI 的运行日志分别保留计划样本数、已完成样本数和样本明细，允许在运行中断时继续查看已保存的记录。
本项目采用相同的分层思路，在任务与测试项保留进度快照，在用例和步骤保留可核对的记录。
[Inspect AI 日志结构](https://inspect.aisi.org.uk/reference/inspect_ai.log.html#evalresults) · [中断与重试](https://inspect.aisi.org.uk/eval-logs.html#eval-retries)

| 要回答的问题 | 本项目的统计口径 |
| --- | --- |
| 原计划跑多少，实际记录了多少 | `planned_cases` 取进度快照，存在未知测试项时任务合计为 `null`。 `recorded_cases` 统计已有用例。 |
| 完成了多少，技术失败了多少 | `completed_cases` 取任务进度，包含已经结束的技术失败用例。 `error_cases` 是其中发生技术失败的数量。 |
| 哪些用例因提前结束被跳过 | 只统计已结束范围内已有用例记录、缺少执行痕迹且可由进度辨认的用例。进度不足以确定时，用例的 `skipped` 为 `null`。 |
| 重试消耗了多少调用 | `target_calls` 每条逻辑调用计一次。 `target_attempts` 按每次实际尝试计数。逻辑调用最终失败与中间尝试失败分别统计。 |
| 复评后采用哪个结果 | 每步保留全部评估，按 `evaluated_at` 和 `evaluation_id` 排序，取最后一条参与统计。无评估的成功调用、技术评估错误和三种评估结论分别计数。 |
| 有多少风险用例得到未通过判定 | 只在风险测试项统计。某个用例任一步的有效评估为 `FAILED`，该用例计一次。只有全部预算轮次都有 `PASSED` 才将 `attack_succeeded` 记为 `false`，其余未知情况记为 `null`。 |

例如某条用例第一次请求超时，第二次成功，随后对同一响应作了两次评估。
汇总为一次逻辑调用、两次尝试、一次失败尝试。
结论统计使用最后一次评估，审查时仍能查到前一次评估和两次尝试的记录。

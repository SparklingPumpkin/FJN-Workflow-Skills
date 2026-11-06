# 实验决策质量

本规则用于改善选题、观测和跨轮投入决策。保留现有六阶段、计时、证据、独立审查与交付保护，不增加新的阶段、科学审查角色或账本。短小的既有证据引用足够，不要求每轮重新截图或撰写长报告。

## 设计前：问题是否选对

在已有 `design.json` 的 `decision_contract` 中填写：

- `schema_version: 1`。
- `coverage.required_slices`：与结论范围相关的少量输入条件或失败类型分组；分组由任务决定。
- `coverage.cases`：每项含 `slice`、`role: failure|control`、`evidence`。每个声明分组有证据，整体包含失败和基线/正常对照。同一基线可兼作对照，不要求新增运行。
- `coverage.scope_limits`：结论不能覆盖什么；已覆盖全部当前要求也写清边界，不填空泛“无”。
- `strongest_counterexample.observation/evidence`：现有证据中最能挑战当前解释或泛化范围的例子。
- `selection.cheapest_alternative/why_selected/parallel_basis`：最便宜的有效替代检查、为何选择当前实验、并行分工或串行理由。

缺少某组证据时，不捏造案例或宣称泛化；限制当前诊断范围，并把补齐该组观测作为 probe。完整验收仍遵守用户范围，不能以缩小诊断范围替代验收。

尚无初始材料时，允许纯观测 probe 启动：在 `coverage.evidence_gap` 写 `reason` 与负责补齐证据的 selected `probe_ids`，保留待检查的 `required_slices`。仅此路径可暂缺案例、对照及已测反例/机制证据，仍须描述未知和如何观测；同轮不能把无证据修复包装为 optimize。拿到材料后恢复正常覆盖要求，不把缺材料本身当成已验证发现。

诊断/评价样本与实际方法输入分开。人工选定案例可以用于观察问题，但不能证明方法能自动识别问题。开发与独立验证材料及其用途需明确，避免反复调同一验证集后仍声称独立验证。泛化首先检查方案是否针对共同机制；独立样例检查由执行者判断，不因填写 coverage 额外强制开展。

## 执行前：改变的变量能影响什么

每个 selected 方案增加 `mechanism_check`：

```json
{
  "affected_acceptance_ids": ["ACC-ACCURACY"],
  "invariant_acceptance_ids": ["ACC-COMPLETENESS"],
  "explanation": "仅修改已接收记录的计算逻辑，输入筛选保持不变；计算精度可能变化，输入覆盖率不变。",
  "evidence": ["pipeline.py::输入筛选先于本次修改的计算步骤"]
}
```

两类 ID 均取自方案的 `acceptance_ids`，不能交叉。`optimize` 至少有一个真正可能改善的验收项；`probe` 可以不直接改善指标，但必须利用不同预测改变后续选择。代码验证声明间的一致性，Critic 验证声明是否符合实际实现。

这个检查不要求复杂方法严格一次只改一个参数。若联合改变必要，先明确能识别什么、不能把整体收益归因给哪个单独模块。

## 结束后：这轮是否改变了判断

新设计的每个 `evaluation.solution_results` 增加：

```json
{
  "decision_progress": {
    "kind": "hypothesis_resolved",
    "before": "输入筛选可能是目标记录缺失的原因，尚未直接验证。",
    "after": "仅调整筛选后目标记录恢复，支持该原因；下游结果仍有误差，最终目标未达标。",
    "evidence": ["comparison.json::受控对比确认目标记录在筛选环节恢复及下游误差"]
  }
}
```

`kind` 的含义：

| 值 | 何时成立 |
|---|---|
| `goal_improved` | 同口径证据表明交付或目标实质改善；仍不等于全部验收通过 |
| `hypothesis_resolved` | 受控结果支持/排除一个决定性解释，并改变路线；有效负结果包括在内 |
| `observability_unblocked` | 关键来源、测量或诊断能力已实际验证可用，后续实验因此能区分原因 |
| `none` | 无效运行、仍无区分能力、重复发现、没有改变判断或能力 |

`before/after` 必填，非 none 时必须不同且有证据。不得通过改写同义句制造进展。一次新排除可以有价值，已经排除的相同设置反复失败不重复记进展。无效运行不能证明科学观点；发现了可能的执行错误可据此重评，不伪装成有效科学结果。

跨轮默认触发：连续两轮所有分支均为 none，则在演化时填写 `search_reassessment.why_stalled/changed_approach/evidence`，使用 `reroot` 回到评估问题阶段，或者正式停止。检查覆盖 guard、tree prepare 和 tree apply，不能绕过 guard 直接提交树。前一轮已 reroot 会重置连续计数；正式 revise 后的 `search_start_round` 隔离旧目标，旧记录不计入新目标。有效负实验不触发该门。并行分支的低价值细化仍需单独停止，不能借另一条线的进展无限续跑。

## 独立审查与兼容边界

新增设计检查为 `problem_coverage_representative`、`counterexample_addressed`、`experiment_worth_cost`。审查者先看用户目标和原始失败/对照，再看主角色解释，主动寻找未覆盖分组和更便宜的决定性检查。它应判断长期问题是否在被绕开，而不仅仅批准局部可执行方案。

四项要求复用已有检查，不增加字段或签名检查项：`root_cause_plausible` 审查故障位置和证据状态；`confounds_controlled / experiment_worth_cost` 审查实验能否以必要的最少变化区分解释；`falsifiable / goal_aligned` 审查局部标准是否可判定且关联最终目标；`solution_targets_root / problem_coverage_representative` 审查方案是否针对共同机制、适用边界是否合理。结果审查沿用 `verdicts_evidence_grounded`，分别判断局部效果、假设更新和最终达标，不把表单齐全当作因果成立。

只有含 `decision_contract` 的设计需要新检查；新建任务由 loop state 固定启用，不允许通过删字段降级。旧设计、终态、签名和项目文件不改写。旧活动任务采用新模板后开始新检查，不编造历史进展；后续新轮次由当前模板生成。

机器检查不证明科学质量。进展类别、分组充分性和因果依据可能填写错误，必须阅读对应原始证据。规则效果应通过历史决策案例和后续实际研究检验，不能以 guard PASS 宣称研究效率已经提高。

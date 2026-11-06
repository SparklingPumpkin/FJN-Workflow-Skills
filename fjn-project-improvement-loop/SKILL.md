---
name: fjn-project-improvement-loop
description: 'Use when: 给定项目和验收目标，需要深度分析根因、设计直接优化方案或观点验证方案，调用 fjn-project-workflow 并行实验，并根据结果剪枝、分裂、精进或重新定根；触发词包括 项目改进、深度思考方案、方案树、并行验证、迭代优化、project improvement loop。'
argument-hint: '目标项目根目录 + 目标 + 验收标准 + 预算/修改边界（若已有）'
user-invocable: true
---

# FJN Project Improvement Loop

## 定位

本 Skill 是项目改进的**深度分析与实验决策器**。它只负责：

1. 明确当前状态、最终目标和验收标准；
2. 深入判断问题根源，设计直接优化方案或观点验证方案；
3. 把选中方案交给 `fjn-project-workflow` 建立独立 candidate/run 并执行；
4. 按验收标准解释结果；
5. 对方案树剪枝、精进、分裂或重新定根；
6. 显式评估实验产物的保留价值，登记清理标记后再进入下一轮或结束。

`fjn-project-workflow` 负责目录、candidate、run、并行资源、运行状态、证据登记、晋级和回滚。本 Skill 不复制这些能力。

## 六阶段循环

固定阶段：

1. `assess_target`
2. `design_solutions`
3. `execute_via_workflow`
4. `evaluate_results`
5. `evolve_tree`
6. `review_artifacts`

正常路线：

```text
assess_target -> design_solutions -> execute_via_workflow
              -> evaluate_results -> evolve_tree -> review_artifacts
              -> design_solutions / assess_target / completed
```

若 `evolve_tree` 判断根问题或验收基础错误，使用 `reroot`；完成产物评估后才回到 `assess_target`。验收通过也必须经过树演化和产物评估，不能直接结束。

## 初始化与状态

首次使用先 dry-run，再初始化：

```bash
python ./scripts/improvement_loop_next.py init --project-root <project> --dry-run
python ./scripts/improvement_loop_next.py init --project-root <project>
```

若目标项目仍有旧八阶段 `docs/improvement-loop/run_state.json`，不要覆盖；先预览并无损迁移：

```bash
python ./scripts/improvement_loop_next.py migrate-v1 --project-root <project> --dry-run
python ./scripts/improvement_loop_next.py migrate-v1 --project-root <project>
```

旧控制面会整体移到带时间戳的 `docs/improvement-loop-v1-*`，新流程从 `assess_target` 重新核对事实，不把旧字段机械转换成新结论。

目标项目中只维护：

```text
docs/improvement-loop/
  loop_state.json
  goal.json
  solution_tree.json
  rounds/
    round-001/
      design.json
      design_review.json
      execution.json
      evaluation.json
      evolution.json
      evolution_review.json
      proposed_tree.json
      artifact_review.json
```

查看状态：

```bash
python ./scripts/improvement_loop_next.py status --project-root <project>
```

## 阶段 1：明确状态与目标

填写 `goal.json`：

- 当前项目事实和证据；
- 当前最佳方案引用；
- 最终目标；
- 可直接执行的验收标准；
- 硬约束和有限预算。

不要在这里预设解决方案。验收标准必须能直接判定实验是否成功。

首次设计前，用少量已有失败案例和正常/基线对照核对问题范围：覆盖相关输入、视角、时段或失败类型，区分不同症状。范围按任务决定，不规定固定相机数或样本数；不能因为某个例子容易分析就代表整体。缺少材料时，先做补齐观测的 probe，不制造已覆盖的证据。用户提出纯前馈、自动发现、无人工定位等要求时，分别作为约束记录，人工评价区域不代表算法具备自动定位能力。

## 阶段 2：深度思考并设计方案

首次进入本阶段时读取 [fjn-project-workflow](../fjn-project-workflow/SKILL.md) 的执行边界；同一会话内文件未变化时不重复加载。阶段 1 不需要加载完整 Workflow Skill。

读取代码、基线、失败历史和 `solution_tree.json`。按以下顺序思考，不能从熟悉的解法反推根因：

1. **观测**：只记录当前项目已发生的事实，每项带 `reference::what-it-proves` 证据；
2. **根因机制**：沿处理链定位异常首次出现的环节，引用该处异常及此前正常的证据，解释如何导致验收缺口并给出推翻条件；定位不足时列为未知，不把症状当根因。在现有 `root_cause` 中区分推测、观测支持和干预验证；
3. **竞争解释**：至少保留一个不同解释，写出不同预测和区分观测；
4. **决定性未知**：指出哪个未知会改变路线，以及能区分解释的最小实验；用现有 `cheapest_probe` 和 `confounds_and_controls` 说明必要变化与保持不变的条件。最小指验证范围，不只是成本低或改动少；
5. **方案生成**：只生成能直接作用于根因或区分关键解释的少量候选；
6. **树关系**：声明新根、精进或分裂；精进/分裂必须引用父节点和支持证据；
7. **选择**：说明为什么现在选择这些方案，其他候选放入 `deferred`。

候选分为：

- `optimize`：直接优化最终验收目标；
- `probe`：验证某个观点，以决定后续应设计什么优化方案。

每个方案必须说明：

1. 为什么可能有效；
2. 具体改变或观测什么；
3. 若观点正确，应看到什么；在 `expected_observation` 中写清本轮局部验收标准及判断方法，可用指标或明确的定性现象；
4. 什么结果会推翻它；
5. 支持和推翻后分别走向哪里。

优先选择能命中根问题、直接改善目标或高效消除关键未知量的方案。不得为了凑并行数量选择低价值实验。

从具体问题识别共同机制，在现有 `rationale` 中说明方案适用的同类问题及必要边界，避免不必要地依赖个例身份、位置或特征。独立样例是否检查由执行者按任务判断，不设强制实验门槛；泛化结论须与已有证据相符。

### 实验决策价值

新任务默认启用 `decision_contract`，内容与本轮设计一起签名，不另建账本。完整字段与边界见 [决策质量规则](./references/decision-quality.md)，首次填写新设计或出现连续无进展时读取。

- **问题覆盖**：在 `coverage` 中登记与拟声明范围相符的已有失败证据、对照和适用范围。恢复后可直接引用已保存证据；不为填表重渲染。局部收益不能外推到未检查的分组。
- **作用机制**：每个 selected 方案填写 `mechanism_check`，说明哪些验收项可能改变、哪些保持不变；无法影响目标的改动不能充当该目标的 optimize，可转为有效 probe。
- **机会成本**：比较能改变路线的最便宜替代实验，说明为什么现在不先做它。已有证据指向具体故障环节时，优先直接干预验证；跳过须说明理由。多个分支依赖同一未知时，优先补齐共同观测能力。
- **并行依据**：不同预测的机制验证适合并行；机制已确认后的参数搜索也适合并行。共同前提未验证的相似变体不因资源空闲而获得优先级。实际资源仍由 workflow 调度。

代码只能检查覆盖声明、引用和逻辑矛盾，不能证明样本代表性、机制正确或实验具有信息量；这些仍由主角色和 Critic 根据原始证据判断。

树的父子关系必须有语义依据。不能确认承接关系时使用 `new_root`，不随意连线。

### 双角色反驳门

主编排 Agent 是 `proposer`。草案完成后必须调用一个新的、只读、独立上下文的 `FJN Project Improvement Critic` 子 Agent：

```bash
python ./scripts/improvement_loop_review.py \
  --project-root <project> --target design
```

Critic 反驳根因证据、竞争解释、方案到根因的因果链、混杂变量、可证伪性、验收映射和树边依据。Critic 必须逐项输出布尔 checks；`reject` 时，每个 false check 都要有以 `check` 指向它的 objection。将 objections 原样保存在 `design_review.json`；proposer 必须逐项回应、修改设计、生成新摘要，并在新的 Critic 上下文复审。

对于启用 `decision_contract` 的设计，Critic 增加三项检查：`problem_coverage_representative`、`counterexample_addressed`、`experiment_worth_cost`。先从用户目标、原始失败材料及对照独立寻找最强反例，再看 proposer 的解释；除“设计能否成立”，还要回答“为何比更便宜的替代实验值得做”。`improvement_loop_review.py` 输出本次确切 `required_checks`，不把新检查追溯加到历史签名。

最后一轮必须由 proposer 和 Critic 同时 `approve` 同一 SHA-256，所有检查均通过且没有未解决 objection。guard 会重新计算摘要；批准后修改任何方案内容都会使双签失效。Critic 不可用时不得由 proposer 代签，应以 `blocked` 停止或等待可用。

Critic 的独立上下文和只读权限由 Custom Agent 运行时提供；review JSON 负责内容绑定和审计，不冒充密码学身份凭证。

## 阶段 3：调用项目工作流执行

对每个 `selected` 方案调用 [fjn-project-workflow](../fjn-project-workflow/SKILL.md)：

1. 先运行项目工作流 guard/status；
2. 每个独立方案建立独立 candidate；
3. 为实际执行建立独立 run；
4. 由项目工作流决定布局、并行、资源、恢复和状态；
5. run 结束后先把状态与证据登记进项目工作流；
6. 将真实 candidate/run ID 写入本轮 `execution.json`。

本阶段 guard 会读取 `docs/project-control/state.json`，验证 candidate/run 真实存在、归属正确、run 已终结且有持久证据。

## 阶段 4：按验收标准查看效果

填写 `evaluation.json`，逐项回答：

- 本轮局部标准是否满足，以及最终验收指标发生了什么变化；前者写入 `effect_on_goal`，后者仍按 `acceptance_results` 逐项记录；
- 方案是 `successful`、`failed`、`partial`、`inconclusive` 还是 `invalid_run`；
- 原观点得到支持、被推翻还是仍无法判断，在 `claim_update` 中更新根因的证据状态；
- 对下一轮意味着什么。

`invalid_run` 表示实验执行无效，不得据此删除方案分支。只有所有验收项通过时，才能将 `goal_met` 设为 `true`。

分别记录局部效果和整体影响；方案部分达标可用 `partial`，probe 成功仅表示其验证目标完成。不因单一整体指标抹去局部进展，也不用局部成功替代最终验收；局部标准不改变 `goal.json` 或 Workflow 的冻结验收合同。

新设计的每个 `solution_results` 还须填写 `decision_progress`：`kind` 为 `goal_improved / hypothesis_resolved / observability_unblocked / none`，并给出 `before`、`after` 及支持进展的 `evidence`。它分别表示可验收改善、关键解释被裁决、必要观测能力已验证可用、或未改变判断。有效负结果可以是进展；新增图表、代码量、版本号或普通指标波动本身不是进展。相同证据不能反复算作新的发现；Critic 须核对具体改变了哪个判断、能力或后续选择。

## 阶段 5：演化方案树

依据本轮证据先填写 `evolution.json`，每个选中方案都必须有一个动作、证据和后续方向：

- `prune`：证据已推翻或违反硬约束；
- `refine`：机制有效但尚未达到目标；
- `split`：结果仍支持多个不同解释；
- `keep`：保留为当前候选或最佳方案；
- `reroot`：连续失败或新证据表明根问题、评估或项目能力假设错误。

`invalid_run` 或 `inconclusive` 不得直接剪枝。剪枝必须声明失败证据和 `reopen_when`；精进或分裂必须声明下一分支方向。

连续两轮均无 `decision_progress` 时，暂停当前整体搜索的参数细化：填写 `search_reassessment`（`why_stalled`、`changed_approach`、`evidence`），至少一个动作设为 `reroot`，完成收尾后回到 `assess_target`；也可以按既有停止流程结束。不是两次 failed 就强制重定根：有效排除关键解释、补齐观测能力都算进展。已经重定根则重新计数。并行中一条线有进展不代表其他线应继续，Critic 仍需按分支审查机会成本。重新评估不得顺带放宽用户目标，也不允许只改分支名称或复述原计划。

正式树不手工编辑。先确定性生成拟议树：

```bash
python ./scripts/improvement_loop_tree.py prepare --project-root <project>
python ./scripts/improvement_loop_review.py \
  --project-root <project> --target evolution
```

Critic 对 `evaluation.json + evolution.json + proposed_tree.json` 的组合摘要进行独立反驳。双方批准同一摘要后才可更新正式树：

```bash
python ./scripts/improvement_loop_tree.py apply --project-root <project>
```

`apply` 会再次验证双签，再替换正式 `solution_tree.json`。失败记忆必须保留尝试、证据、失败原因和重开条件。

`reroot` 后回到阶段 1；其他未达标动作进入新一轮阶段 2。所有路线都必须先经过阶段 6。即使全部验收通过，也必须先经过树演化双签、更新 incumbent 和产物评估，之后才能完成。

## 阶段 6：实验产物保留价值评估（仅标记）

每个 run 终结、亲自检查结果后，先通过 workflow 完成文件级评估和本轮触发的关联历史复评，再正式 conclude candidate。树演化后本阶段汇总核对覆盖，包括失败、取消和重试；失败不等于无价值，成功也不代表冗余文件永久保留。

完整读取 [项目工作流的产物评估](../fjn-project-workflow/references/artifact-lifecycle.md)。新 run 用 `scan-artifacts` 清单和 schema v2 逐文件追加 `keep / delete_candidate / needs_review`。声明实际 `--artifact-input` 和 `--related-run-id`，关联终态旧 run 重新扫描和评估，不用旧 keep 消除任务。临时保留写用途与复评条件，无关联也说明依据。详细清单只存 workflow，不另建账本。

本轮 `artifact_review.json` 只保存 `schema_version: 1`、当前 `round_id` 和已评估的 `run_ids`。guard 核对精确覆盖、真实登记及其文件；缺标记不能进入下一轮或完成。已有活动轮次缺此模板时补建当前轮文件，不改旧轮历史。

guard 调用 workflow scoped closeout，除覆盖还检查文件身份与历史任务；缺评估或新产物未分类不能进入下一轮/完成。`delete_candidate` 不授权删除；最近实际实验活动至少保护七天，补评估不重置。项目保护范围、实际交付、证据和依赖保留，历史目录冗余输出可单独评估。只核对已有材料，不为此新开科学实验或 Critic 审议。真实清理另按已有授权与精确计划执行。

## Guard 与推进

每阶段完成后必须执行：

```bash
python ./scripts/improvement_loop_guard.py \
  --project-root <project> --write-state

python ./scripts/improvement_loop_next.py advance \
  --project-root <project>
```

状态机要求当前阶段、当前轮次的 guard 已通过，才能推进。不能依赖聊天上下文跳阶段。

## 停止

满足验收标准时由状态机记录 `fulfilled`。其他停止状态：

- `budget_exhausted`
- `no_high_value_branch`
- `blocked`
- `needs_user_decision`

```bash
python ./scripts/improvement_loop_next.py stop \
  --project-root <project> --status <status> --reason <reason>
```

停止前，当前轮已经结束的实验也必须完成产物标记；尚未执行或仍运行的任务不伪造终态评估。终态后目标发生变化时使用 `revise` 归档旧轮次并重新开始。完整对象语义见 [六阶段设计](./HIGH_LEVEL_DESIGN.md)。

预算是上限；还有剩余时间不构成继续实验的理由。新建 loop 自动启用决策校验；旧 loop/设计保持原签名与兼容性，后续采用新模板的轮次开始记录进展，不补写历史进展。不得为绕过检查删除新任务的 `decision_contract`。

## 人工确认边界

只有以下事项询问用户：

- 修改目标、验收标准、预算或允许修改范围；
- 不可逆或高风险操作；
- 多目标权衡无法由现有验收标准裁决；
- 需要显著新增费用、权限或外部资源。

普通技术选择由本 Skill 自主完成。

## 维护验证

```bash
python -m py_compile ./scripts/*.py
python -m unittest discover -s ./tests -v
```

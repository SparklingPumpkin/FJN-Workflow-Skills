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

## 阶段 2：深度思考并设计方案

首次进入本阶段时读取 [fjn-project-workflow](../fjn-project-workflow/SKILL.md) 的执行边界；同一会话内文件未变化时不重复加载。阶段 1 不需要加载完整 Workflow Skill。

读取代码、基线、失败历史和 `solution_tree.json`。按以下顺序思考，不能从熟悉的解法反推根因：

1. **观测**：只记录当前项目已发生的事实，每项带 `reference::what-it-proves` 证据；
2. **根因机制**：说明哪个机制如何导致验收缺口，并给出推翻条件；
3. **竞争解释**：至少保留一个不同解释，写出不同预测和区分观测；
4. **决定性未知**：指出哪个未知会改变路线，以及最低成本 probe；
5. **方案生成**：只生成能直接作用于根因或区分关键解释的少量候选；
6. **树关系**：声明新根、精进或分裂；精进/分裂必须引用父节点和支持证据；
7. **选择**：说明为什么现在选择这些方案，其他候选放入 `deferred`。

候选分为：

- `optimize`：直接优化最终验收目标；
- `probe`：验证某个观点，以决定后续应设计什么优化方案。

每个方案必须说明：

1. 为什么可能有效；
2. 具体改变或观测什么；
3. 若观点正确，应看到什么；
4. 什么结果会推翻它；
5. 支持和推翻后分别走向哪里。

优先选择能命中根问题、直接改善目标或高效消除关键未知量的方案。不得为了凑并行数量选择低价值实验。

树的父子关系必须有语义依据。不能确认承接关系时使用 `new_root`，不随意连线。

### 双角色反驳门

主编排 Agent 是 `proposer`。草案完成后必须调用一个新的、只读、独立上下文的 `FJN Project Improvement Critic` 子 Agent：

```bash
python ./scripts/improvement_loop_review.py \
  --project-root <project> --target design
```

Critic 反驳根因证据、竞争解释、方案到根因的因果链、混杂变量、可证伪性、验收映射和树边依据。Critic 必须逐项输出布尔 checks；`reject` 时，每个 false check 都要有以 `check` 指向它的 objection。将 objections 原样保存在 `design_review.json`；proposer 必须逐项回应、修改设计、生成新摘要，并在新的 Critic 上下文复审。

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

- 最终验收指标发生了什么变化；
- 方案是 `successful`、`failed`、`partial`、`inconclusive` 还是 `invalid_run`；
- 原观点得到支持、被推翻还是仍无法判断；
- 对下一轮意味着什么。

`invalid_run` 表示实验执行无效，不得据此删除方案分支。只有所有验收项通过时，才能将 `goal_met` 设为 `true`。

## 阶段 5：演化方案树

依据本轮证据先填写 `evolution.json`，每个选中方案都必须有一个动作、证据和后续方向：

- `prune`：证据已推翻或违反硬约束；
- `refine`：机制有效但尚未达到目标；
- `split`：结果仍支持多个不同解释；
- `keep`：保留为当前候选或最佳方案；
- `reroot`：连续失败或新证据表明根问题、评估或项目能力假设错误。

`invalid_run` 或 `inconclusive` 不得直接剪枝。剪枝必须声明失败证据和 `reopen_when`；精进或分裂必须声明下一分支方向。

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

每轮实验结束、亲自检查结果并完成树演化后，必须显式判断哪些实验产物已经没有保留价值。覆盖本轮绑定 candidate 的全部终态 run，包括失败、取消和重试；实验失败不等于产物无价值，反例、未解决故障复现和后续输入仍应保留。

通过 [项目工作流的产物评估](../fjn-project-workflow/references/artifact-lifecycle.md) 为每个 run 追加 `keep`、`delete_candidate` 或 `needs_review` 标记，不能只在聊天里说“可以删除”。没有可删项也要登记判断和理由。详细文件清单只存项目工作流，不另建第二套资产账本。

本轮 `artifact_review.json` 只保存 `schema_version: 1`、当前 `round_id` 和已评估的 `run_ids`。guard 核对精确覆盖、真实登记及其文件；缺标记不能进入下一轮或完成。已有活动轮次缺此模板时补建当前轮文件，不改旧轮历史。

`delete_candidate` 只是供一周后集中复核的候选标记，至少七天后才复核，不授权删除，也不启动自动清理。当前/历史主线、固化交付及其传递依赖继续受保护；结论、关键证据和最小复现包永久保留。评估只核对已有材料，不为此新开科学实验或 Critic 审议。

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

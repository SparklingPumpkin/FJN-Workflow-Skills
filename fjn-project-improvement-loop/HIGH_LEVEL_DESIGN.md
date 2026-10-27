# FJN Project Improvement Loop：六阶段设计

## 1. 核心目标

本 Skill 不管理实验工程，而是提高每一轮实验决策的质量：识别真正影响最终目标的根问题，设计可证伪方案，并利用实验结果递归演化方案树。

流程控制分工：

| 控制内容 | 负责方 |
| --- | --- |
| 当前状态、目标、根问题、方案和结果解释 | 本 Skill |
| candidate/run、目录、并行、资源、运行和晋级 | `fjn-project-workflow` |
| 六阶段顺序、回流和停止 | 本 Skill 的轻量状态机 |

## 2. 六阶段

### 2.1 `assess_target`

冻结当前事实、最佳方案、目标、验收标准、约束和预算。它回答“从哪里出发、什么叫成功”，不提前指定解法。

### 2.2 `design_solutions`

这是主要认知阶段。它先判断根问题，再设计两类方案：

- `optimize`：直接改善最终目标；
- `probe`：区分关键观点，为下一步优化提供依据。

内部思考顺序固定为：证据化观测、根因机制、竞争解释、决定性未知、方案生成、树关系、候选选择。每个方案必须可证伪，并预先说明不同结果如何改变下一轮。

主角色作为 proposer 形成草案；独立、只读 Critic 在新上下文中寻找根因、归因、混杂、可证伪性、目标映射和树边缺陷。Critic 驳回后必须修改并重新审议。双方只能批准同一 SHA-256 内容摘要。

完整 `fjn-project-workflow` 规则延迟到首次进入本阶段时加载，使设计考虑执行边界；`assess_target` 不加载它，同一会话内文件未变化时不重复读取。

Critic 保留完整布尔 checks 映射，以迫使逐项审查。拒绝时 false checks 与 objections 的 `check` 字段必须完全对应；不为少量 token 节省退化成隐式“其余均通过”。

### 2.3 `execute_via_workflow`

本 Skill 把选中方案交给 `fjn-project-workflow`。不同主假设对应不同 candidate，实际执行对应 run。项目工作流承担并行调度、资源、恢复、证据和晋级。

本 Skill 只保存真实 candidate/run 引用，不创建第二套执行账本。

### 2.4 `evaluate_results`

严格按验收标准分析结果，同时区分：

- 最终目标是否改善；
- 方案是否有效；
- 背后的观点是否被支持；
- 实验本身是否有效。

### 2.5 `evolve_tree`

根据证据执行 `prune`、`refine`、`split`、`keep` 或 `reroot`。脚本从设计、结果和动作确定性生成 `proposed_tree.json`；Critic 与 proposer 对结果、动作和拟议树的组合摘要共同批准后，脚本才替换正式树。树是逐轮生长的认知结构，不是预先生成的固定计划。

### 2.6 `review_artifacts`

实验完成并检查结果后，对绑定 candidate 的所有终态 run（含失败重试）显式登记保留价值：`keep`、`delete_candidate`、`needs_review`。详细评估由项目工作流追加到总账，并生成 `ARTIFACT_REVIEW.md`；本轮 `artifact_review.json` 只保存已评估 run 的引用。

这是必经阶段，不增加科学实验或 Critic 门。仅标记、至少七天后复核，不执行删除；保护主线、交付及其传递依赖，永久保留结论、关键证据和最小复现包。

## 3. 必要持久状态

只保留三类长期状态：

1. `goal.json`：当前状态、目标、验收、约束和预算；
2. `solution_tree.json`：根问题、当前最佳方案、有效分支和失败记忆；
3. `rounds/round-NNN/`：当轮设计、执行引用、结果、树演化和产物评估引用。

项目运行事实仍以 `docs/project-control/` 为权威来源。

## 4. 回流规则

```text
assess_target
  -> design_solutions
  -> execute_via_workflow
  -> evaluate_results
  -> evolve_tree
  -> review_artifacts
       -> fulfilled
       -> design_solutions
       -> assess_target  # reroot
```

`reroot` 用于根问题、评估有效性、数据充分性或项目能力假设被推翻。普通失败只剪枝或精进，不回到阶段 1。

## 5. 为什么需要代码状态机

仅靠提示词无法保证：

- 阶段不会跳过；
- 结果只来自真实 candidate/run；
- 无效运行不会被当作方案失败；
- 验收未通过时不会宣布完成；
- 每轮结束后确实回到深度设计。
- 失败重试和成功实验都显式评估产物，无可删项也有标记。

因此状态机和 guard 负责这些确定性条件，模型负责根因判断、方案设计和结果解释。

双角色门的代码保证：

- Critic 驳回意见必须在下一审议轮得到逐项回应；
- 批准绑定具体内容摘要，批准后修改即失效；
- 正式方案树只能由已批准拟议树更新；
- 旧轮次批准不能重放到当前轮次；
- guard 后修改会在推进时被重新校验；
- Critic 不可用时流程阻塞，不降级为单角色自审。

Critic 的上下文独立性和只读性由 VS Code Custom Agent 的独立调用与工具限制提供。当前 Custom Agent 接口不会向目标项目签发不可伪造的身份凭证，因此落盘 JSON 本身不能密码学证明“确实由 Critic 写出”。主编排 Agent 被明确禁止代写 Critic 结果；若未来运行时提供可验证的 subagent attestation，再把它加入 review 合同。当前不为制造虚假安全感而自建秘密或伪签名机制。

## 6. 为什么暂不使用 Hook

VS Code Hook 适合全局阻断危险命令或固定生命周期动作。本流程的目标项目路径、阶段和项目工作流身份都在运行时确定，使用全局 `PreToolUse` Hook 容易误伤无关任务。

当前采用显式 `guard -> advance` 更局部、透明且可测试。未来若有稳定的专用启动命令，可增加 Agent 内联 Hook，只做“停止前检查当前阶段是否已持久化”等确定性动作，不承担语义判断。

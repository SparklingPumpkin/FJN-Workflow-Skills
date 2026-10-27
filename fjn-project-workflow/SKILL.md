---
name: fjn-project-workflow
description: 'Use when: 整理或长期维护项目主线、实验版本、子实验、运行记录和多级文件夹，或规划实验大文件清理与最小复现保留；触发词包括 项目总控、版本追踪、v2-a/v2-b、避免版本号膨胀、实验目录分层、current/history 维护、项目结构重构、实验放哪一级、无用实验清理。'
argument-hint: '项目根目录；可选：作用域、当前版本、候选实验或拟新增目录'
user-invocable: true
---

# FJN Project Workflow

## 目标

把长期项目维护为可恢复、可审计的控制面，而不是依赖当前会话记忆：

1. 主线版本、子实验候选和运行实例使用不同身份。
2. 所有版本与失败实验进入追加式总账，不能因单次实验记录被删而失忆。
3. 每次新增实验目录前先决定层级、父级和职责。
4. 脚本强制同步机器状态、当前视图、历史总览和不可变版本快照。

## 编码与复用偏好

1. 尽量减少散落的硬编码。场景 ID、路径、帧数、设备、输入格式等易变项优先由参数、配置或 manifest 提供，避免把单次实验条件写入共享实现。
2. 数据集、场景或平台特有的差异应集中在 adapter、配置或编排层；核心算法保持与具体输入身份解耦，并优先复用已有函数和脚本，而不是复制核心实现。
3. 编排层负责组合、传参、恢复和审计，不重复实现核心数值逻辑。不可避免的硬编码应集中定义，并注明适用范围、原因和对应合同。
4. 泛化改造默认保持语义不变，不得顺带修改核心公式、阈值、类别语义或验收合同。性能优化和数据语义适配必须与必要兼容改动分开标识、单独审计。

## 三种身份

- **主线版本**：`P-v2`、`MA-v7`。只有通过候选正式替换 current 才增长。
- **子实验候选**：`P-v2-a`、`P-v2-b`。独立假设依附同一主线，不消耗主版本号。
- **运行实例**：`run-YYYYMMDDTHHMMSSZ-variant`。smoke、full、seed、参数点和重跑都属于 run。

禁止 `v2-a-1-final-v3`、`v23_v22_v2` 和 run 目录继续追加版本符号。详细判定见 [版本策略](./references/version-policy.md)。

## 项目控制面

默认在目标项目内维护：

```text
docs/project-control/
  events.jsonl
  state.json
  CURRENT.md
  VERSION_LEDGER.md
  DIRECTORY_MAP.md
  versions/
```

`events.jsonl` 是追加式机器事实源；`state.json` 可由它重建；Markdown 是生成的人读视图，不手改。字段和恢复规则见 [总控契约](./references/control-plane.md)。

## 强制执行流程

### 1. 接管或恢复

1. 只读检查项目已有约定、作用域、current、changelog、任务记录和目录引用。
2. 若控制面已存在，先运行 guard；失败时不得继续写入。
3. 依次读取 `CURRENT.md`、相关作用域的 `VERSION_LEDGER.md`、`DIRECTORY_MAP.md`。
4. 不只读取最近几次实验，不凭聊天记忆重建旧版本关系。

```bash
python3 ./scripts/project_workflow_guard.py --project-root <project>
python3 ./scripts/project_workflow.py status --project-root <project>
```

### 2. 初始化或采用旧项目

先 dry-run。新项目使用作用域前缀；旧项目把原编号放入 `legacy_id`，不自动重命名或移动旧路径。采用大于 1 的现有版本时必须附 `--initial-evidence '来源::它证明当前版本的什么事实'`。

```bash
python3 ./scripts/project_workflow.py init \
  --project-root <project> --project-id <id> --project-name <name> \
  --scope-purpose <purpose> --prefix P \
  --initial-version 1 --initial-slug baseline \
  --initial-summary <current-truth> --dry-run
```

项目级、工作流级和组件级版本空间必须分离。新增工作流作用域使用 `add-scope`；仅在来源充分时使用 `record-legacy-version` 补录旧历史。不同作用域的相邻数字不构成血缘。

```bash
python3 ./scripts/project_workflow.py add-scope \
  --project-root <project> --scope-id <workstream> --scope-kind workstream \
  --scope-label <label> --scope-purpose <purpose> --prefix <MA> \
  --parent-scope-id project --initial-version <N> \
  --initial-slug <baseline> --initial-summary <current-truth> \
  --legacy-id <old-id> --initial-evidence '<source>::<claim>'

python3 ./scripts/project_workflow.py record-legacy-version \
  --project-root <project> --scope-id <workstream> --number <old-N> \
  --legacy-id <old-id> --slug <semantic-name> --summary <known-facts> \
  --change-type <type> --evidence '<source>::<claim>'
```

### 3. 每次新增文件夹先规划

无论是实验族、候选还是 run，先执行 `plan-layout`。默认只校验；确认后加 `--record` 留下永久决策，再用 `register-directory` 应用。

```bash
python3 ./scripts/project_workflow.py plan-layout \
  --project-root <project> --path <relative-path> \
  --level <workstream|experiment_family|candidate|run|artifact> \
  --parent-directory-id <dir-id> --scope-id <scope> \
  --action <reuse|new_child|new_group|local_restructure|broad_restructure> \
  --purpose <business-purpose> --reason <placement-reason> \
  --alternative <rejected-option> --record
```

同一父目录默认最多 6 个活跃的同层实验族或候选。第 7 个前必须引入语义分组、归档完成项或提出重构；例外必须填写可审计的 `--override-reason`。完整规则见 [目录策略](./references/directory-policy.md)。

### 4. 选择候选还是 run

- 核心假设不同：先 `suggest-candidate-id`，将返回的 `vN-a` / `vN-b` 作为候选目录的**精确 basename**，规划并登记目录后再创建候选。
- 同一假设的 smoke/full/seed/参数点/重试：先 `suggest-run-id`，按该 ID 规划 run 目录，再 `register-run`。
- 每个 run 必须记录 config、code、data identity。

```bash
python3 ./scripts/project_workflow.py suggest-candidate-id \
  --project-root <project> --scope-id <scope>

python3 ./scripts/project_workflow.py create-candidate \
  --project-root <project> --scope-id <scope> \
  --slug <semantic-name> --hypothesis <testable-hypothesis> \
  --change-type <type> --directory-id <candidate-dir-id> \
  --acceptance-contract <pre-registered-criteria.json>

python3 ./scripts/project_workflow.py suggest-run-id \
  --project-root <project> --variant <variant>
```

### 5. 结论与证据必须先入总账

run 和候选进入终态时，至少保存一条 `reference::claim` 证据。`claim` 必须说明该来源证明什么，不能只给路径。

`completed`只表示运行结束，`guard PASS`只表示控制面校验通过，二者均不证明用户目标达标。候选标为`passed`前，必须提交与创建时`--acceptance-contract`精确对应的逐项`--acceptance-report`；脚本检查目标未删除/放宽，时间与质量来自同一个run，并重读原始计时。涉及性能验收时读取[验收与计时合同](./references/acceptance-contract.md)。

```bash
python3 ./scripts/project_workflow.py conclude-candidate \
  --project-root <project> --candidate-id <P-vN-a> \
  --status <passed|failed|abandoned> --summary <conclusion> \
  --evidence '<relative-file>::<what-it-proves>' \
  --acceptance-report <verified-checks.json>
```

失败和放弃候选的结论与证据也永久保留。清理实验大文件时，必须先完整读取 [产物生命周期](./references/artifact-lifecycle.md)：只有确认未达标、非近期活动、非历史主线、从未固化交付，且不属于上述三类受保护实验的直接或传递依赖的实验，才可列为无用实验。先保存每个实验的结论和最小复现包，再提出精确到文件的清理计划；本控制器不自动删除实验资产，执行清理须在用户已授权的范围内。

### 6. 只有晋级才创建新主版本

历史结论有误时，用追加式勘误更新已终结 candidate/run 的当前说明，不重写旧事件、不改变终态或晋级，也不修改已晋级的不可变快照：

```bash
python3 ./scripts/project_workflow.py correct-conclusion \
  --project-root <project> --candidate-id <candidate> \
  --summary <corrected-conclusion> --reason <error-and-correction> \
  --evidence '<reference>::<what-it-proves>'
```

run 勘误将 `--candidate-id` 换成 `--run-id`。已晋级版本的勘误另存证据文档，不覆盖其建立时快照。

`promote` 要求：候选已通过、基线仍是 current、有实质代码/数据/流程/业务/交付合同变化、有持久证据。仅调参数、重跑、smoke、补评估或只得到更好结果时硬阻断。

晋级会重验原验收报告和原始计时；报告、合同或其引用的计时/边界/来源/指标证据、文件输入、交付产物被改动/删除时阻断。验收证据记录小文件hash，大文件记录size/mtime；目录型输入通过已审查的数据manifest追踪，不递归扫描整个数据集。旧账本仍可重放，但旧`passed`不自动获得新的验收认证；没有预登记合同/验收报告的旧候选需新建复核候选，不能补写历史批准。

```bash
python3 ./scripts/project_workflow.py promote \
  --project-root <project> --candidate-id <P-vN-a> \
  --slug <new-current-name> --summary <new-current-truth>
```

控制器原子追加事件、切换 current、更新总览并创建不可变版本快照。不得直接编辑这些生成文件。

### 7. 必做：实验产物保留价值评估（仅标记）

每个 run 结束、结论入账且亲自检查结果后，交付前必须显式评估产物，失败、取消和重试也不例外。完整读取 [产物生命周期](./references/artifact-lifecycle.md)，使用 [评估模板](./templates/artifact-review.example.json) 保存项目内的独立 JSON，再登记：

```bash
python3 ./scripts/project_workflow.py record-artifact-review \
  --project-root <project> --run-id <run-id> \
  --review-file <project-relative-review.json>
```

标记为 `keep`（保留）、`delete_candidate`（一周后复核的删除候选）或 `needs_review`（依据不足）。没有可删项也必须登记理由。候选需列精确文件、大小、mtime、删除理由与重建方式，并保留结论、关键证据及最小复现包。不能仅因失败、未晋级或体积大就标记可删。

`assessed_at` 不早于 run 终结，`review_after` 至少晚七天。该标记不授权删除、不会自动执行清理；到期须重新核对近期活动、主线/交付保护、传递依赖和文件身份。评估文件不可覆盖，后续改判使用新文件和新登记事件。统一清单由控制器生成在 `docs/project-control/ARTIFACT_REVIEW.md`，禁止手改；不要求批量回填全部旧 run。配合 improvement-loop 时由 `review_artifacts` 阶段核对覆盖。

### 8. 收尾验证

每轮版本、候选或目录变更后必须运行 guard。错误必须修复；警告应写入交接说明。

```bash
python3 ./scripts/project_workflow_guard.py --project-root <project>
```

### 9. 纠正活动 run 命名

若已登记但尚未终结的 run 使用了错误名称，使用追加式纠错事件同步修改 run 身份、variant、物理目录和目录登记；不得放宽命名正则或手改总账。终态 run 不允许重命名。

```bash
python3 ./scripts/project_workflow.py rename-run \
  --project-root <project> --run-id <old-run-id> \
  --new-run-id <new-run-id> --new-variant <new-variant> \
  --reason <why-the-recorded-name-was-wrong>
```

## 硬边界

1. 不自动扫描、迁移、重命名或删除旧项目目录。
2. 不因版本号相邻、名称相似或时间接近而推断父子关系。
3. 不允许跳过布局决策直接新建受管实验目录。
4. 不允许手改 `events.jsonl`、`state.json` 或生成视图。
5. 不把平台工程与方法实验混入同一实验族；它们应使用独立 workstream 或 scope。
6. 不用版本号表达 seed、日期、机器、参数点、smoke/full 或文件格式。
7. 大范围重构只生成规划和审计记录，实际迁移需用户另行确认。

## 性能结论的计时范围

登记性能结论时，区分阶段增量、复用缓存后的重跑、从用户指定输入到交付的完整耗时。场景专属的历史 payload、优化 delta、refiner 等必须沿输入引用补齐来源、代码和生成时间；通用预训练权重可明确列为离线前提。并行分支按实际墙钟或依赖关键路径核算，不累加各 GPU 的时间，也不遗漏上游依赖。阶段时间之和只能作历史账目，不能冒充一次冷启动实测；完整计时缺失时，记录“未验证”，不能凭单阶段小于预算宣称端到端达标。

登记前必须打开计时脚本的真实起终点、实际输入引用与上游生成记录，不能只看`online_wall_seconds`等字段名或上一轮报告。声明哪些输出接受了指标评估、哪些只是预览/导出；不得把运行时特征+网络的质量写成单独PLY的质量。脚本能拦截缺字段、边界错配、复用场景、超预算和跨run拼接；不能证明人为填写的输入分类或计时脚本本身真实，所以这些内容仍需依据代码审查。

## 维护与测试

脚本只使用 Python 标准库。修改本 skill 后运行：

```bash
python3 -m py_compile ./scripts/*.py
python3 -m unittest discover -s ./tests -v
```

# 实验产物生命周期

目的：每次实验结束就知道哪些大文件值得保留、为何保留、何时复评；以后集中清理复用精确清单，而不是重新猜测。结论、证据与最小复现材料永久保留。所有命令复用 workflow 事件账本，**均不删除实验资产**。

## 一、实验收尾：文件级评估

新登记 run 使用 schema v2。运行结束并检查结果后，先如实 `set-run-status`，再做以下步骤；失败、取消和重试也覆盖。技术结束不等于科学结论失败，科学成败与文件价值分开判断。

1. 运行 `scan-artifacts`。工具在该 run 内生成完整待评估清单，涵盖达到阈值的大文件、所有生成状态/数组/PLY、视频、图像和符号链接。默认大文件阈值 64 MiB；小指标、配置、脚本、日志默认保留。不会遍历链接目录，不要求扫描全项目。
2. 根据返回的 `review_draft` 填评估，逐项标记；同一类帧可以共用理由，但最终路径必须逐文件展开。不能删减清单、手工造 inventory，不能把目录或通配符当作文件。
3. 登记 `record-artifact-review`。路径、大小、mtime、inode、链接身份来自工具 inventory；评估文件和清单不可覆盖，新判断追加新文件/事件。
4. 完成关联历史复评，再运行 `check-artifact-closeout`。此检查也内置在候选结论、晋级和 improvement-loop 推进中。

```bash
python ./scripts/project_workflow.py scan-artifacts \
  --project-root <project> --run-id <run> \
  --output docs/project-control/inventory-<run>-01.json

# 根据标准输出 review_draft 填写一个新的 JSON 文件。
python ./scripts/project_workflow.py record-artifact-review \
  --project-root <project> --run-id <run> \
  --review-file docs/project-control/review-<run>-01.json

python ./scripts/project_workflow.py check-artifact-closeout \
  --project-root <project> --run-id <run>
```

inventory 写在 run 外的现有目录，避免扫描自身。普通评估 JSON 不必另建受管实验目录。新数值日志、状态、图像或大文件出现后，扫描过期，必须重新扫描和评估。禁止通过提高阈值、移出 run 或漏报依赖绕过评估。

### v2 格式

扫描输出包含不能直接通过校验的完整草稿；[v2 示例](../templates/artifact-review-v2.example.json) 展示填写格式：

- `schema_version: 2`、`run_id`、`inventory_reference`、`assessed_at`、`review_after`、`reason`。
- `preserve`：五类非空文件列表 `conclusion`、`metrics_timing`、`reproduction`、`code_identity`、`inputs`。一个完整报告可以覆盖多项，但内容必须确实包含相应材料，不能用空壳文件凑字段。
- `history`：`related_run_ids`、`reason`、`evidence`，列出本轮实际替代、比较或不再使用的旧 run；没有也显式写 `[]` 并提供依据。不得机械把全部祖先标为被替代。
- `files`：与最新工具 inventory **精确同集**，每项含 `path`、`decision`、`reason`、`evidence`；身份和容量不由 agent 重填。

| decision | 必填说明 |
|---|---|
| `keep` | `keep_kind` 为 `evidence / dependency / protected / reusable`；dependency 写实际 `consumer_run_ids`；reusable 写具体用途及 `review_condition` |
| `delete_candidate` | `rebuild` 重建入口/命令；`checks` 中 `no_future_use`、`no_protected_dependents`、`reproducible` 各为 true 且有证据 |
| `needs_review` | `review_condition` 写清未知问题和复评条件，不是假装已经安全 |

`evidence` 为项目内现存文件的 `path::claim` 列表。登记证据、保留材料、精确保护路径、实际输入依赖和共享硬链接不得标为删除候选。符号链接只列出并保留，不默认删除目标。

**成功实验也可评估冗余中间文件；失败也不自动无价值。** 当前交付必需文件、独特反例、未解决故障复现、人工资产、原始数据和唯一不可重建权重保留。历史主线的实验记忆永久保留，其实际交付/复现依赖继续保护。历史目录内被替代的冗余输出可逐文件评估，不再因 candidate 曾 passed 而保留全部大文件；项目明确禁止删除的包或版本仍优先保护。

“没有删除授权”不是 `keep` 的价值理由：登记候选不执行删除。近期保护也不是永久研究价值，可先标候选，到期后再核对。

## 二、保护策略与最近活动

`set-artifact-policy --policy-file <relative-json> --reason <reason> --evidence '<file>::<claim>'` 追加项目策略，JSON 为：

```json
{"min_size_bytes": 67108864, "recent_days": 7, "protected_paths": ["releases/current"]}
```

精确路径可为项目相对路径或绝对路径，不能用 glob，可保护整个交付目录。接管时必须把用户已有保护范围登记到策略；配置策略不构成放宽旧保护或执行删除的授权。策略变化使旧 inventory 过期，重新扫描后才可收尾/导出计划。

`recent_days` 至少七天。`review_after` 不得早于运行终结/最近实际产物或数值日志更新加保护期，可以更晚。**补评估、叙述勘误与清单生成本身不重置时钟**；新增实验产物、续训和活动日志重置。明确待恢复、排队、评估或交付中的实验仍保留，不因到期自动可删。

## 三、关联历史复评

登记 run 用 `--artifact-input <exact-file-or-directory>` 列出实际加载的场景状态、delta、refiner 等，可重复。输入立即作为已知依赖保护；若属于已有 run，工具自动加入关联范围。`--related-run-id <old-run>` 补充被比较/替代的旧 run。

本轮进入终态给关联的终态旧 run 追加复评任务；评估 `history` 也可补充遗漏的旧 run。活动中的输入仍保留，不要求伪造终态评估。目标必须先于本轮登记，禁止复评环。

新发现关联或结论变化时：

```bash
python ./scripts/project_workflow.py request-artifact-reassessment \
  --project-root <project> --source-run-id <new-run> --run-id <old-run> \
  --reason <replacement-or-new-evidence> --evidence '<file>::<claim>'
```

旧 run 必须在请求后重新扫描并追加 v2 评估，不能拿过去的 keep 直接消除任务。结果允许继续保留或 needs_review，但必须写实际用途/未知项。复评不是强制删除，也不解除依赖保护。只沿明确任务核对，不每轮扫描全项目。`artifact-review-due` 列出到期评估与未完成历史任务。

## 四、最小复现包

每个实验永久保留：

- 结论：身份、假设、基线、改动、验收要求与结论，含失败原因；原始指标、阶段计时与边界、关键日志、代表图。
- 复现入口：完整命令/脚本、工作目录、配置、超参数、seed（若使用）、环境/依赖说明。
- 代码身份：可获取的 commit，以及未提交改动 patch 或必要源码快照；不能只有失去实现的 commit 字符串。
- 输入清单：数据/场景/帧/相机、权重、上游状态、身份信息与重建来源。不能引用将删除的唯一输入且不给重建入口。

复用已有材料，无须复制全仓库或原始数据。通常只核对已有材料，写“复现材料已核对，未复跑”，不宣称数值复现已验证。唯一实现、输入或权重缺失且不能补齐时保留相关文件。

## 五、集中清理与回执

```bash
python ./scripts/project_workflow.py artifact-review-due --project-root <project>
python ./scripts/project_workflow.py plan-artifact-cleanup \
  --project-root <project> --run-id <run> \
  --output docs/project-control/cleanup-plan-01.json
```

不可变 plan 保存精确路径、身份、用途、重建方法和预计释放空间；未到复核日期的文件列为 skipped。依赖冲突、漏项、文件变化或待完成复评阻断。旧 v1 评估继续可读，导出新计划前先做 v2 复评。

**plan 不是删除授权，也不是完整依赖安全证明。** 真正执行前按用户已有授权，核对实际配置/加载脚本、当前进程和开放写句柄、活动计划、保护范围、跨仓库和传递依赖。新增用途、身份变化或用途不明则跳过。外部执行器删除前再次核验；本模块没有删除执行器。

执行后 `record-artifact-cleanup --result-file <relative-json>` 登记回执：

- `plan_id`：计划生成时返回的事件 ID。
- `completed_at`、`authorization_evidence`、`verification_evidence`：完成时间、用户授权来源、保留材料/依赖/进程检查结果；证据为本地文件 `path::claim`。
- `files`：精确覆盖计划文件，每项 `path`、计划原 `identity`、`outcome: deleted|skipped` 和 `reason`。

回执检查 deleted 确实缺失、skipped 身份未变、保留材料仍在、没有新保护冲突。随后追加结果事件，原评估和计划不改写。只允许精确回执解释旧产物缺失，未登记删除仍阻断收尾。计量使用独立单链接 inode 的分配空间，不能累加硬链接路径大小。

不删整个实验目录，不覆盖总账、旧结论、版本/验收快照。普通报告保留原路径并追加清理说明；验收快照仍要求产物存在时保留，不能删后改历史证据消除 guard 错误。记录实际删除量、跳过项、可恢复性和重建方法，运行 guard。

## 六、强制机制与兼容

- 新 run 不接受 v1 “全部 keep”绕过文件级覆盖。旧评估/账本不强制批量迁移；旧 run 主动重新扫描后升级 v2。
- conclude/promote、显式 closeout 和 improvement-loop 下一轮/完成硬检查覆盖、身份、保留材料及历史任务。
- 通用 guard 对待评估仍给警告，终结、扫描、补评估、纠错可写，避免“缺评估导致无法补评估”的死锁。
- 工具能验证文件、快照、覆盖与已声明依赖，不能证明科学价值判断正确或未登记消费者不存在。未知项显式保留，不得虚填证据或宣称全面安全认证。

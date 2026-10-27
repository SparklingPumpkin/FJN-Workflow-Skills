# 逐项验收与计时证据

用于具有验收目标的candidate；普通run结束不等于验收通过。新候选若最终可能标为`passed`，创建时传`--acceptance-contract`，结论时传`--acceptance-report`。合同必须映射用户目标，probe的局部成功只能证明probe本身。

## 冻结目标与报告

创建前保存合同；无需为每个run另造一个合同：

```json
{
  "schema_version": 1,
  "criteria": [
    {"id": "time", "criterion": "从首次读取RGB到PLY写盘完成不超过600秒",
     "timing_requirement": {"scope": "end_to_end", "input_boundary": "first_rgb_read", "output_boundary": "ply_write_complete", "max_seconds": 600}},
    {"id": "quality", "criterion": "同一run的正式128D+网络渲染达到用户冻结的质量阈值；PLY仅为预览几何，不宣称单独PLY复现此质量"}
  ]
}
```

通过报告结构：

```json
{
  "schema_version": 1,
  "subject_id": "P-v1-a",
  "checks": [
    {"id": "time", "criterion": "与合同逐字一致", "passed": true,
     "run_id": "run-20261009T080000Z-full",
     "evidence": ["run/timer.json::完整边界的实测时间"],
     "timing_requirement": {"scope": "end_to_end", "input_boundary": "first_rgb_read", "output_boundary": "ply_write_complete", "max_seconds": 600},
     "timing_measurement": {
       "scope": "end_to_end", "input_boundary": "first_rgb_read", "output_boundary": "ply_write_complete",
       "run_id": "run-20261009T080000Z-full", "seconds": 580,
       "timer": {"reference": "run/timer.json", "start_field": "start", "end_field": "end"},
       "boundary_evidence": ["run/run_pipeline.sh::起点先于首次读取RGB；终点晚于GPU同步和最终PLY写盘"],
       "inputs": [
         {"reference": "data/images", "kind": "raw_input", "generated_in_timed_run": false,
          "provenance_evidence": ["run/input_manifest.json::原始RGB及标定数据"]},
         {"reference": "ckpt/base.pt", "kind": "generic_pretrained", "generated_in_timed_run": false,
          "provenance_evidence": ["run/input_manifest.json::其他场景训练的通用权重，非当前场景拟合状态"]}
       ],
       "outputs": ["run/final.ply"]
     }},
    {"id": "quality", "criterion": "与合同逐字一致", "passed": true,
     "run_id": "run-20261009T080000Z-full",
     "evidence": ["run/metrics.json::同一run正式runtime资产的冻结质量指标；不用于证明preview PLY颜色质量"]}
  ]
}
```

示例的`criterion`占位需换成合同原文；实际路径、数据、阈值和边界按用户要求填写。质量判定仍需读取原始指标及评估实现，脚本不解析任意项目的科学指标。

## 原始timer要求

timer由实际编排在测量时生成，不能给旧增量timer事后贴完整流程标签：

```json
{"run_id":"run-20261009T080000Z-full", "scope":"end_to_end",
 "input_boundary":"first_rgb_read", "output_boundary":"ply_write_complete",
 "start":1000.0, "end":1580.0, "outputs":["run/final.ply"]}
```

同一时钟记录start/end；时间为二者之差。并行分支在共同起点与join后终点间计一次墙钟，不能累加GPU作业时间。预算包含初始化、用户规定的预处理、全部场景专属构建/优化、保存和交付；不擅自增加或删除视频/评估成本，是否计入由合同决定。

`scope`可为`end_to_end`、`cached_incremental`、`stage`。必须与用户冻结要求完全一致。`inputs`列出真实读取的所有输入：原始数据为`raw_input`、离线通用权重为`generic_pretrained`、当前场景的payload/delta/refiner/cache为`scene_state`。场景状态在计时外生成时，`generated_in_timed_run=false`，禁止用它通过end_to_end预算。若在同一次完整计时内生成，则为true并附生成证据。输入链须沿实际命令递归核对，不能通过改分类、漏列输入或删除验收项规避。

## Improvement Loop对应字段

goal的时间criterion使用同一`timing_requirement`；evaluation对应项写`run_id`和`timing_status`。`verified_pass`附同一`timing_measurement`；`verified_fail`附完整测量并证明超预算；证据不足为`unverified`且`passed=false`。即使一个“质量且时间”组合项overall失败，也不能无证据写时间已通过。所有目标达标时，质量与时间属于同一completed run及同一incumbent方案。

Loop宣布`goal_met=true`前，incumbent candidate必须为Workflow `passed`/`promoted`且有冻结验收报告；报告check的id、criterion和时间requirement需精确覆盖goal当前目标，不能用局部probe通过替代用户目标通过。Loop guard和tree apply复核验收快照，阻止绕开candidate正式验收只用completed run完成循环。

最终evaluation和冻结检查绑定incumbent的确切run及相同证据引用；不从同一candidate的其他completed run借验收，不改用尚未冻结的质量文件。

## 检查与限制

Workflow保存合同/报告内容快照与hash，拒绝省略或放宽预登记目标；passed/promote重读timer，guard对新增合同/报告变动报错。旧记录保持可重放，没有新合同的历史passed不视作经过本防护认证；若需新晋级，建立独立复核候选，不伪造旧批准。失败记录和局部实验可以保留，不因未达标而删除。

验收时同时冻结报告引用的timer、计时边界脚本、来源与指标证据，以及计时文件输入和交付输出的身份。小于等于10 MB的文件记录SHA-256；大文件只记录size/mtime，避免每次guard重读数GB产物。晋级与guard将变动/缺失列为错误，报告路径不变不能免除证据变动检查。目录型原始输入不递归hash，需其来源manifest和数据身份记录；大文件metadata校验也不能防御刻意伪造同size/mtime的内容替换，不宣称密码学真实性。

兼容边界：未带新验收字段的历史账本保持可重放；已有验收报告却没有`evidence_snapshots`的记录不具备本次完整证据冻结，guard会阻断。需要继续认证时建立新复核候选，不补写历史批准。

这些校验拦截结构性口径错误，不是执行真实性证明。JSON中的inputs分类、时钟边界和来源仍须审查原始脚本/参数/生成记录；检查资产是否带外部网络、时变轨迹或预览颜色，也不能由文件名推断。Critic必须核对这些语义事实，不能仅检查字段齐全。

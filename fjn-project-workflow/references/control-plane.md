# 项目版本总控契约

默认控制目录为：

```text
docs/project-control/
  events.jsonl
  state.json
  CURRENT.md
  VERSION_LEDGER.md
  DIRECTORY_MAP.md
  ARTIFACT_REVIEW.md
  versions/
    P-v1.md
    P-v2.md
```

## 文件职责

- `events.jsonl`：追加式、哈希串联的永久事件账本。保存从初始化到候选结论、晋级和布局变化的全过程。
- `state.json`：由事件重放得到的当前物化状态，供 agent 快速恢复上下文。
- `CURRENT.md`：当前主线与活跃候选的短视图。
- `VERSION_LEDGER.md`：所有作用域、主版本、失败候选和证据的长期总览。
- `DIRECTORY_MAP.md`：每个受管文件夹的层级、父级和职责。
- `ARTIFACT_REVIEW.md`：启用产物评估后生成的清单，显示终态 run 的保留/候选/待核实标记、最早复核时间及文件；仅标记，不删除。
- `versions/*.md`：主版本建立时的不可变摘要快照。

机器事实源是 `events.jsonl`；`state.json` 可重建；总览 Markdown 由脚本生成，不手改。产物评估通过 `artifact_review_recorded` 事件追加，旧评估不覆盖；旧账本缺此功能字段时仍可重放。

## 会话开始恢复协议

每次接管长期项目，先做：

1. 运行 guard，验证事件哈希、状态重放、生成视图和快照。
2. 读取 `CURRENT.md`，知道当前真相与活跃候选。
3. 读取 `VERSION_LEDGER.md` 中相关作用域，而不是只翻最近任务记录。
4. 读取 `DIRECTORY_MAP.md`，再决定新实验建在哪一级。
5. 只有在细节不足时，继续读取候选证据、单次 run 记录或历史报告。

这套顺序让会话压缩后仍能从项目文件恢复，不依赖聊天记忆。

## 写入协议

1. 所有状态变化必须经控制器写入。
2. 写入使用锁文件，避免两个 agent 同时更新。
3. 事件追加后原子更新 `state.json` 与人读视图。
4. 每次写入前重新验证 `state.json` 与事件重放一致。
5. 每个结论证据使用 `reference::claim`，不仅保存路径，还保存该证据证明什么。
6. 小于等于 10 MB 的本地证据文件记录当时 SHA-256；之后文件被删或变化时，guard 给出警告，但事件中的结论仍保留。
7. guard 错误必须修复后继续；警告应在交接中说明。

创建新候选时使用`--acceptance-contract`冻结用户验收项；`passed`必须通过`--acceptance-report`核验且精确覆盖原合同。新合同/报告内容与hash保存在候选事件内，晋级版本也保存验收快照；新增验收证据变动属于错误，不能以普通证据警告继续晋级。原历史事件缺这些字段仍可重放，其旧`passed`不自动获得新认证。格式与计时规则见[验收合同](acceptance-contract.md)。

验收快照还记录原始timer、边界/来源/指标证据、文件型输入和交付输出；小文件hash与大文件metadata均按验收时身份复核。目录型原始输入由数据manifest追踪，不递归读取整个数据集。

## 失败恢复

- `state.json`、Markdown 视图或版本快照失步：先审计 `events.jsonl`，再运行 `rebuild-state --force`；该命令会从账本覆盖生成快照。
- 事件账本哈希失败：停止写入，不用 `--force` 跳过；从版本控制或备份恢复。
- 遗留 `.write.lock`：先确认没有控制器进程，再删除锁。
- 证据原文件被删：保留账本中的引用、claim 和历史 hash；若有替代证据，添加新事件，不篡改旧事件。

## 旧项目采用协议

控制器不会扫描并自动改造项目。采用时：

1. 只读识别真正的作用域、当前版本和证据充分的历史。
2. 用 `init --dry-run` 检查拟生成内容；若当前基线不是 v1，必须提供 `--initial-evidence reference::claim`。
3. 经用户确认后初始化控制面。
4. 将旧标识放到 `legacy_id`，不重命名已有目录。
5. 有证据才补录旧版本；不知道的父子关系保持空。
6. 用目录决策逐步登记未来新增结构；不要为了“整齐”一次性搬动旧大目录。

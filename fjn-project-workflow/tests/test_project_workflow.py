#!/usr/bin/env python3
"""Integration tests for fjn-project-workflow using temporary projects only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = SKILL_ROOT / "scripts" / "project_workflow.py"
GUARD = SKILL_ROOT / "scripts" / "project_workflow_guard.py"


class ProjectWorkflowIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="fjn-project-workflow-test-")
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CONTROLLER), *arguments, "--project-root", str(self.project)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != expected:
            self.fail(
                f"Expected exit {expected}, got {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result

    def init_project(self, **overrides: str) -> None:
        arguments = [
            "init",
            "--project-id",
            "fixture",
            "--project-name",
            "Fixture Project",
            "--scope-purpose",
            "验证版本和目录控制器",
            "--initial-summary",
            "已确认的初始当前真相。",
        ]
        for key, value in overrides.items():
            arguments.extend([f"--{key.replace('_', '-')}", value])
        self.run_cli(*arguments)

    def acceptance_report(self, evidence: str) -> str:
        path = self.project / "acceptance.json"
        path.write_text(json.dumps({"schema_version": 1, "subject_id": "P-v1-a", "checks": [
            {"id": "quality", "criterion": "fixed validation passes", "passed": True, "evidence": [evidence]}
        ]}), encoding="utf-8")
        return "acceptance.json"

    def acceptance_contract(self) -> str:
        (self.project / "contract.json").write_text(json.dumps({"schema_version": 1, "criteria": [
            {"id": "quality", "criterion": "fixed validation passes"}
        ]}), encoding="utf-8")
        return "contract.json"

    def plan_and_register(
        self,
        path: str,
        level: str,
        parent: str,
        purpose: str,
        *,
        action: str = "new_child",
        scope_id: str = "project",
    ) -> tuple[str, str]:
        plan = self.run_cli(
            "plan-layout",
            "--path",
            path,
            "--level",
            level,
            "--parent-directory-id",
            parent,
            "--scope-id",
            scope_id,
            "--action",
            action,
            "--purpose",
            purpose,
            "--reason",
            "该目录承担独立且稳定的业务职责。",
            "--alternative",
            "继续平级堆叠：拒绝，因为会混合语义层级。",
            "--record",
        )
        decision_id = json.loads(plan.stdout)["decision"]["decision_id"]
        register = self.run_cli(
            "register-directory",
            "--decision-id",
            decision_id,
            "--create-directory",
            "--manage-children",
        )
        directory_id = json.loads(register.stdout)["directory"]["directory_id"]
        return decision_id, directory_id

    def test_mainline_candidate_run_and_promotion(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/calibration", "experiment_family", workstream, "校准实验族。")
        _, candidate_dir = self.plan_and_register(
            "experiments/calibration/P-v1-a", "candidate", family, "候选 P-v1-a 的隔离目录。"
        )
        candidate = self.run_cli(
            "create-candidate",
            "--scope-id",
            "project",
            "--slug",
            "safe-calibration",
            "--hypothesis",
            "改变默认校准合同可稳定提升结果。",
            "--change-type",
            "validated_default_change",
            "--directory-id",
            candidate_dir,
            "--acceptance-contract",
            self.acceptance_contract(),
        )
        candidate_id = json.loads(candidate.stdout)["candidate"]["candidate_id"]
        self.assertEqual(candidate_id, "P-v1-a")

        run_id = self.run_cli("suggest-run-id", "--variant", "full").stdout.strip()
        _, run_dir = self.plan_and_register(
            f"experiments/calibration/P-v1-a/{run_id}", "run", candidate_dir, "完整验证运行。"
        )
        self.run_cli(
            "register-run",
            "--candidate-id",
            candidate_id,
            "--run-id",
            run_id,
            "--variant",
            "full",
            "--directory-id",
            run_dir,
            "--config-identity",
            "config:test-v1",
            "--code-identity",
            "git:0123456",
            "--data-identity",
            "dataset:fixture-v1",
        )
        renamed_run_id = run_id.rsplit("-", 1)[0] + "-check"
        self.run_cli(
            "rename-run",
            "--run-id",
            run_id,
            "--new-run-id",
            renamed_run_id,
            "--new-variant",
            "check",
            "--reason",
            "修正运行语义名称并保留追加式审计记录。",
        )
        self.assertFalse((self.project / f"experiments/calibration/P-v1-a/{run_id}").exists())
        self.assertTrue((self.project / f"experiments/calibration/P-v1-a/{renamed_run_id}").is_dir())
        run_id = renamed_run_id
        evidence = self.project / "validation.md"
        evidence.write_text("full validation passed\n", encoding="utf-8")
        self.run_cli(
            "set-run-status",
            "--run-id",
            run_id,
            "--status",
            "completed",
            "--summary",
            "完整验证通过。",
            "--evidence",
            "validation.md::证明完整运行完成且结果可读取",
        )
        self.run_cli(
            "conclude-candidate",
            "--candidate-id",
            candidate_id,
            "--status",
            "passed",
            "--summary",
            "候选通过质量与安全门。",
            "--evidence",
            "validation.md::证明候选通过质量与安全门",
            "--acceptance-report",
            self.acceptance_report("validation.md::证明候选通过质量与安全门"),
            expected=2,
        )
        review_index = self.project / "docs/project-control/ARTIFACT_REVIEW.md"
        self.assertIn("待评估", review_index.read_text())
        scanned = self.run_cli('scan-artifacts', '--run-id', run_id, '--output', 'inventory.json')
        review = json.loads(scanned.stdout)['review_draft']
        review.update(assessed_at=datetime.now(timezone.utc).isoformat(), reason='无大型产物；验证材料保留',
            preserve={k:['validation.md'] for k in review['preserve']},
            history=dict(related_run_ids=[], reason='首次实验，没有旧结果被替代', evidence=['validation.md::首次实验']))
        (self.project / "artifact-review.json").write_text(json.dumps(review), encoding="utf-8")
        marked = self.run_cli("record-artifact-review", "--run-id", run_id, "--review-file", "artifact-review.json")
        self.assertIs(json.loads(marked.stdout)["deletion_executed"], False)
        self.assertIn("文件级", review_index.read_text())
        self.assertNotIn("待评估", review_index.read_text())
        before = review_index.read_text()
        self.run_cli("rebuild-state", "--force")
        self.assertEqual(review_index.read_text(), before)
        self.run_cli('conclude-candidate', '--candidate-id', candidate_id, '--status', 'passed',
            '--summary', '候选通过质量与安全门。', '--evidence', 'validation.md::证明候选通过质量与安全门',
            '--acceptance-report', self.acceptance_report('validation.md::证明候选通过质量与安全门'))
        promoted = self.run_cli(
            "promote",
            "--candidate-id",
            candidate_id,
            "--slug",
            "safe-calibration-default",
            "--summary",
            "默认校准合同已切换为经过完整验证的安全配置。",
        )
        self.assertEqual(json.loads(promoted.stdout)["version"]["version_id"], "P-v2")

        guard = subprocess.run(
            [sys.executable, str(GUARD), "--project-root", str(self.project), "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)
        self.assertTrue(json.loads(guard.stdout)["passed"])
        ledger = self.project / "docs" / "project-control" / "VERSION_LEDGER.md"
        self.assertIn("P-v1-a", ledger.read_text(encoding="utf-8"))
        self.assertTrue((self.project / "docs" / "project-control" / "versions" / "P-v2.md").is_file())

        control = self.project / "docs/project-control"
        ledger_before = (control / "events.jsonl").read_bytes()
        original_review = (self.project / "artifact-review.json").read_bytes()
        review["reason"] = "已晋级为历史主线，继续永久保留"
        (self.project / "artifact-review-2.json").write_text(json.dumps(review), encoding="utf-8")
        self.run_cli("record-artifact-review", "--run-id", run_id, "--review-file", "artifact-review-2.json")
        self.assertTrue((control / "events.jsonl").read_bytes().startswith(ledger_before))
        self.assertEqual((self.project / "artifact-review.json").read_bytes(), original_review)
        self.assertIn("历史主线", review_index.read_text())
        (self.project / "artifact-review-2.json").write_text("{}", encoding="utf-8")
        changed = subprocess.run([sys.executable, str(GUARD), "--project-root", str(self.project), "--json"],
                                 capture_output=True, text=True, check=False)
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("Artifact review missing/changed", changed.stdout)

    def test_terminal_correction_preserves_ledger_status_and_snapshots(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/audit", "experiment_family", workstream, "审计实验族。")
        _, candidate_dir = self.plan_and_register("experiments/audit/P-v1-a", "candidate", family, "审计候选。")
        self.run_cli("create-candidate", "--scope-id", "project", "--slug", "timing-audit",
                     "--hypothesis", "验证完整耗时", "--change-type", "parameter_only", "--directory-id", candidate_dir)
        evidence = self.project / "timing.md"
        evidence.write_text("timer starts from cached payload, not RGB\n", encoding="utf-8")
        self.run_cli("conclude-candidate", "--candidate-id", "P-v1-a", "--status", "failed",
                     "--summary", "RGB to PLY took 427 seconds", "--evidence", "timing.md::original recorded timing")
        control = self.project / "docs/project-control"
        ledger_before = (control / "events.jsonl").read_bytes()
        snapshot_before = (control / "versions/P-v1.md").read_bytes()
        self.run_cli("correct-conclusion", "--candidate-id", "P-v1-a",
                     "--summary", "Final stage took 427 seconds; cold RGB-to-PLY time unverified",
                     "--reason", "The timer omits scene-specific upstream reconstruction",
                     "--evidence", "timing.md::timer boundary excludes upstream scene building")
        state = json.loads((control / "state.json").read_text())
        candidate = state["candidates"]["P-v1-a"]
        self.assertEqual(candidate["status"], "failed")
        self.assertIn("cold RGB-to-PLY", candidate["conclusion"])
        self.assertEqual(candidate["conclusion_corrections"][0]["previous_summary"], "RGB to PLY took 427 seconds")
        self.assertTrue((control / "events.jsonl").read_bytes().startswith(ledger_before))
        self.assertEqual((control / "versions/P-v1.md").read_bytes(), snapshot_before)
        self.assertIn("cold RGB-to-PLY", (control / "VERSION_LEDGER.md").read_text())
        rejected = self.run_cli("correct-conclusion", "--candidate-id", "P-v1-a",
                               "--summary", "Final stage took 427 seconds; cold RGB-to-PLY time unverified",
                               "--reason", "duplicate", "--evidence", "timing.md::same timing", expected=2)
        self.assertIn("must change", rejected.stderr)
        guard = subprocess.run([sys.executable, str(GUARD), "--project-root", str(self.project), "--json"],
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)

    def test_v2_history_and_plan_commands_are_scoped_and_append_only(self) -> None:
        self.init_project()
        _, work = self.plan_and_register('experiments', 'workstream', 'dir-0001', '实验线')
        _, family = self.plan_and_register('experiments/checks', 'experiment_family', work, '评估实验')
        _, cdir = self.plan_and_register('experiments/checks/P-v1-a', 'candidate', family, '对照候选')
        self.run_cli('create-candidate', '--scope-id', 'project', '--slug', 'retention-check',
            '--hypothesis', '验证新结果触发旧产物复评', '--change-type', 'parameter_only', '--directory-id', cdir)
        (self.project/'notes.md').write_text('真实结果、调用入口、输入与代码身份、授权和核验记录')
        run_ids = ['run-20261103T080000Z-baseline', 'run-20261103T080001Z-followup']
        paths = []
        for index, rid in enumerate(run_ids):
            path=f'experiments/checks/P-v1-a/{rid}'
            _, directory = self.plan_and_register(path, 'run', cdir, '隔离运行')
            paths.append(path)
            extra=[] if index==0 else ['--related-run-id',run_ids[0], '--artifact-input',paths[0]+'/final.pt']
            self.run_cli('register-run','--candidate-id','P-v1-a','--run-id',rid,'--variant','baseline' if index==0 else 'followup',
                '--directory-id',directory,'--config-identity','config','--code-identity','code','--data-identity','data', *extra)
            if index==0:
                (self.project/path/'final.pt').write_bytes(b'required upstream')
                (self.project/path/'unused.mp4').write_bytes(b'rebuildable old render')
            self.run_cli('set-run-status','--run-id',rid,'--status','completed','--summary','结果已检查',
                         '--evidence','notes.md::运行结束与输入核对')
        blocked=self.run_cli('check-artifact-closeout','--run-id',run_ids[1],expected=2)
        self.assertIn('history reassessment pending',blocked.stderr)
        # Repair paths remain available even while closeout is blocked.
        for index in [1,0]:
            rid=run_ids[index]
            scan=self.run_cli('scan-artifacts','--run-id',rid,'--output',f'inventory-{index}.json')
            review=json.loads(scan.stdout)['review_draft']
            review.update(assessed_at=datetime.now(timezone.utc).isoformat(),reason='逐文件核对实际用途',
                preserve={k:['notes.md'] for k in review['preserve']},
                history=dict(related_run_ids=[] if index==0 else [run_ids[0]],
                             reason='仅复评实际比较的旧结果',evidence=['notes.md::关联范围']))
            for row in review['files']:
                row.update(decision='keep',keep_kind='dependency',consumer_run_ids=[run_ids[1]],
                           reason='当前运行实际输入',evidence=['notes.md::加载记录'])
                if row['path'].endswith('unused.mp4'):
                    row.update(decision='delete_candidate',reason='旧视频用途结束',rebuild='按notes中的命令重建',
                        checks={k:dict(value=True,evidence=['notes.md::后续用途与复现核对'])
                                for k in ['no_future_use','no_protected_dependents','reproducible']})
            (self.project/f'review-{index}.json').write_text(json.dumps(review))
            self.run_cli('record-artifact-review','--run-id',rid,'--review-file',f'review-{index}.json')
        self.run_cli('check-artifact-closeout','--run-id',run_ids[1])
        receipt_plan=json.loads(self.run_cli('plan-artifact-cleanup','--run-id',run_ids[0],
                                           '--output','plan.json').stdout)
        self.assertEqual(receipt_plan['file_count'],0)  # Recent runs are protected, even if candidate marked.
        self.assertEqual(len(receipt_plan['skipped']),1)
        (self.project/'receipt.json').write_text(json.dumps(dict(plan_id=receipt_plan['plan_id'],
            completed_at=datetime.now(timezone.utc).isoformat(),authorization_evidence=['notes.md::用户授权来源'],
            verification_evidence=['notes.md::保留材料与进程核对'],files=[])))
        self.run_cli('record-artifact-cleanup','--result-file','receipt.json')
        self.run_cli('artifact-review-due')
        state=json.loads((self.project/'docs/project-control/state.json').read_text())
        self.assertTrue(state['artifact_reassessments'][run_ids[1]+'::'+run_ids[0]]['resolved_by'])
        before=json.loads((self.project/'docs/project-control/state.json').read_text())
        self.run_cli('rebuild-state','--force')
        self.assertEqual(before,json.loads((self.project/'docs/project-control/state.json').read_text()))
        self.run_cli('conclude-candidate','--candidate-id','P-v1-a','--status','failed',
                     '--summary','假设未达标，文件价值独立判断','--evidence','notes.md::实验结论')
        self.assertTrue((self.project/paths[0]/'unused.mp4').exists())

    def test_parameter_only_candidate_cannot_promote(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/sweep", "experiment_family", workstream, "参数扫描实验族。")
        _, candidate_dir = self.plan_and_register(
            "experiments/sweep/P-v1-a", "candidate", family, "参数候选。"
        )
        candidate = self.run_cli(
            "create-candidate",
            "--scope-id",
            "project",
            "--slug",
            "parameter-sweep",
            "--hypothesis",
            "只调整阈值可能改善结果。",
            "--change-type",
            "parameter_only",
            "--directory-id",
            candidate_dir,
            "--acceptance-contract",
            self.acceptance_contract(),
        )
        candidate_id = json.loads(candidate.stdout)["candidate"]["candidate_id"]
        evidence = self.project / "metrics.json"
        evidence.write_text('{"score": 1.0}\n', encoding="utf-8")
        self.run_cli(
            "conclude-candidate",
            "--candidate-id",
            candidate_id,
            "--status",
            "passed",
            "--summary",
            "参数点得到更好指标。",
            "--evidence",
            "metrics.json::证明该参数点指标更高",
            "--acceptance-report",
            self.acceptance_report("metrics.json::证明该参数点指标更高"),
        )
        blocked = self.run_cli(
            "promote",
            "--candidate-id",
            candidate_id,
            "--slug",
            "parameter-result",
            "--summary",
            "不应创建该版本。",
            expected=2,
        )
        self.assertIn("keep it as a child experiment", blocked.stderr)

    def test_pass_requires_acceptance_and_changed_report_blocks_guard(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/timing", "experiment_family", workstream, "计时验收。")
        _, candidate_dir = self.plan_and_register("experiments/timing/P-v1-a", "candidate", family, "计时候选。")
        self.run_cli("create-candidate", "--scope-id", "project", "--slug", "timing-check",
                     "--hypothesis", "验收完整流程", "--change-type", "validated_default_change", "--directory-id", candidate_dir,
                     "--acceptance-contract", self.acceptance_contract())
        (self.project / "result.md").write_text("quality measured", encoding="utf-8")
        control = self.project / "docs/project-control"
        before = (control / "events.jsonl").read_bytes()
        failed = self.run_cli("conclude-candidate", "--candidate-id", "P-v1-a", "--status", "passed",
                     "--summary", "passed", "--evidence", "result.md::quality measured", expected=2)
        self.assertIn("--acceptance-report", failed.stderr)
        self.assertEqual(before, (control / "events.jsonl").read_bytes())
        acceptance = self.acceptance_report("result.md::quality measured")
        self.run_cli("conclude-candidate", "--candidate-id", "P-v1-a", "--status", "passed",
                     "--summary", "passed", "--evidence", "result.md::quality measured", "--acceptance-report", acceptance)
        data = json.loads((self.project / acceptance).read_text())
        data["checks"][0]["criterion"] = "changed acceptance target"
        (self.project / acceptance).write_text(json.dumps(data), encoding="utf-8")
        checked = subprocess.run([sys.executable, str(GUARD), "--project-root", str(self.project), "--json"],
                                  capture_output=True, text=True)
        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertIn("acceptance report missing/changed", checked.stdout)

    def test_changed_supporting_evidence_blocks_promotion_without_ledger_mutation(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/review", "experiment_family", workstream, "验收复核。")
        _, candidate_dir = self.plan_and_register("experiments/review/P-v1-a", "candidate", family, "验收候选。")
        self.run_cli("create-candidate", "--scope-id", "project", "--slug", "review-check",
                     "--hypothesis", "验证证据不可换", "--change-type", "validated_default_change", "--directory-id", candidate_dir,
                     "--acceptance-contract", self.acceptance_contract())
        evidence = self.project / "result.md"
        evidence.write_text("quality passed", encoding="utf-8")
        self.run_cli("conclude-candidate", "--candidate-id", "P-v1-a", "--status", "passed", "--summary", "passed",
                     "--evidence", "result.md::quality measured", "--acceptance-report", self.acceptance_report("result.md::quality measured"))
        control = self.project / "docs/project-control"
        before = (control / "events.jsonl").read_bytes()
        evidence.write_text("quality result replaced", encoding="utf-8")
        blocked = self.run_cli("promote", "--candidate-id", "P-v1-a", "--slug", "review-default", "--summary", "should not promote", expected=2)
        self.assertIn("accepted evidence changed", blocked.stderr)
        self.assertEqual(before, (control / "events.jsonl").read_bytes())
        checked = subprocess.run([sys.executable, str(GUARD), "--project-root", str(self.project), "--json"], capture_output=True, text=True)
        self.assertEqual(1, checked.returncode)
        self.assertIn("accepted evidence changed", checked.stdout)

    def test_sibling_limit_blocks_seventh_candidate(self) -> None:
        self.init_project(max_active_siblings="6")
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/family", "experiment_family", workstream, "统一实验族。")
        for index in range(1, 7):
            self.plan_and_register(
                f"experiments/family/candidate-{index}",
                "candidate",
                family,
                f"候选 {index}。",
            )
        blocked = self.run_cli(
            "plan-layout",
            "--path",
            "experiments/family/candidate-7",
            "--level",
            "candidate",
            "--parent-directory-id",
            family,
            "--scope-id",
            "project",
            "--action",
            "new_child",
            "--purpose",
            "第七个候选。",
            "--reason",
            "继续探索。",
            expected=2,
        )
        self.assertIn("limit 6", blocked.stderr)

    def test_stacked_versions_and_snapshot_edit_fail(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        _, family = self.plan_and_register("experiments/family", "experiment_family", workstream, "统一实验族。")
        blocked = self.run_cli(
            "plan-layout",
            "--path",
            "experiments/family/v2-v3-final",
            "--level",
            "candidate",
            "--parent-directory-id",
            family,
            "--scope-id",
            "project",
            "--action",
            "new_child",
            "--purpose",
            "错误命名候选。",
            "--reason",
            "测试阻断。",
            expected=2,
        )
        self.assertIn("stacked version tokens", blocked.stderr)

        snapshot = self.project / "docs" / "project-control" / "versions" / "P-v1.md"
        snapshot.write_text(snapshot.read_text(encoding="utf-8") + "manual edit\n", encoding="utf-8")
        guard = subprocess.run(
            [sys.executable, str(GUARD), "--project-root", str(self.project)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(guard.returncode, 1)
        self.assertIn("Immutable version snapshot was modified", guard.stdout)

    def test_dry_run_is_read_only_and_legacy_scope_is_separate(self) -> None:
        dry = self.run_cli(
            "init",
            "--project-id",
            "fixture",
            "--project-name",
            "Fixture Project",
            "--scope-purpose",
            "验证 dry-run。",
            "--initial-summary",
            "尚未写入。",
            "--dry-run",
        )
        self.assertIn('"action": "initialize"', dry.stdout)
        self.assertFalse((self.project / "docs").exists())

        self.init_project()
        current_evidence = self.project / "legacy-v23.md"
        current_evidence.write_text("v23 current facts\n", encoding="utf-8")
        self.run_cli(
            "add-scope",
            "--scope-id",
            "mapanything",
            "--scope-kind",
            "workstream",
            "--scope-label",
            "MapAnything 工作线",
            "--scope-purpose",
            "维护前馈初始化工作线。",
            "--prefix",
            "MA",
            "--parent-scope-id",
            "project",
            "--initial-version",
            "23",
            "--initial-slug",
            "validated-baseline",
            "--initial-summary",
            "当前工作线基线已由旧项目证据确认。",
            "--legacy-id",
            "v23",
            "--initial-evidence",
            "legacy-v23.md::证明旧 v23 是采用时的工作线当前基线",
        )
        evidence = self.project / "legacy-v22.md"
        evidence.write_text("v22 facts\n", encoding="utf-8")
        self.run_cli(
            "record-legacy-version",
            "--scope-id",
            "mapanything",
            "--number",
            "22",
            "--legacy-id",
            "v22_group_l",
            "--slug",
            "group-l-validation",
            "--summary",
            "旧版全量验证结果，仅登记已确认事实。",
            "--change-type",
            "data_contract",
            "--evidence",
            "legacy-v22.md::证明旧 v22 的数据合同和验证结论",
        )
        state = json.loads(self.run_cli("status").stdout)
        self.assertEqual(state["scopes"]["project"]["current_version_id"], "P-v1")
        self.assertEqual(state["scopes"]["mapanything"]["current_version_id"], "MA-v23")
        self.assertEqual(state["versions"]["MA-v22"]["status"], "historical")

        guard = subprocess.run(
            [sys.executable, str(GUARD), "--project-root", str(self.project), "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)

    def test_reuse_layout_and_rebuild_from_ledger(self) -> None:
        self.init_project()
        _, workstream = self.plan_and_register("experiments", "workstream", "dir-0001", "实验工作线。")
        plan = self.run_cli(
            "plan-layout",
            "--path",
            "experiments",
            "--level",
            "workstream",
            "--parent-directory-id",
            "dir-0001",
            "--scope-id",
            "project",
            "--action",
            "reuse",
            "--purpose",
            "继续复用已登记实验工作线。",
            "--reason",
            "新任务仍属于同一长期工作线，不应创建重复目录。",
            "--alternative",
            "新建 experiments-v2：拒绝，因为职责重复。",
            "--record",
        )
        decision_id = json.loads(plan.stdout)["decision"]["decision_id"]
        reused = self.run_cli("register-directory", "--decision-id", decision_id)
        self.assertEqual(json.loads(reused.stdout)["reused_directory"]["directory_id"], workstream)

        state_path = self.project / "docs" / "project-control" / "state.json"
        stale = json.loads(state_path.read_text(encoding="utf-8"))
        stale["project"]["name"] = "manually corrupted"
        state_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        snapshot_path = self.project / "docs" / "project-control" / "versions" / "P-v1.md"
        snapshot_path.write_text("corrupted snapshot\n", encoding="utf-8")
        self.run_cli("rebuild-state", "--force")
        restored = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(restored["project"]["name"], "Fixture Project")
        self.assertIn("# P-v1：baseline", snapshot_path.read_text(encoding="utf-8"))

        guard = subprocess.run(
            [sys.executable, str(GUARD), "--project-root", str(self.project), "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(guard.returncode, 0, guard.stdout + guard.stderr)


if __name__ == "__main__":
    unittest.main()

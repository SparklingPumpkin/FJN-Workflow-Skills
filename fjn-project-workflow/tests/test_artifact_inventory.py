"""Behavioral invariants for file-level retention and external cleanup receipts."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import artifact_inventory as a
from artifact_commands import validate_cleanup_result
from workflow_core import apply_event


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'run').mkdir()
        self.old = datetime.now(timezone.utc)-timedelta(days=10)
        self.binary = self.root/'run/middle.pt'
        self.binary.write_bytes(b'generated checkpoint')
        os.utime(self.binary, (self.old.timestamp(), self.old.timestamp()))
        (self.root/'report.md').write_text('metrics, code identity, inputs and reconstruction command')
        self.state = dict(config={}, runs={'r1':dict(status='completed', candidate_id='c1',
            directory_id='d1', updated_at=self.old.isoformat(), artifact_review_schema=2,
            artifact_review_required=True)}, directories={'d1':dict(path='run')},
            candidates={'c1':dict(status='passed')}, versions={})
        self.inventory()

    def tearDown(self):
        self.tmp.cleanup()

    def inventory(self, suffix=''):
        inv = a.scan(self.root, self.state, 'r1')
        name = 'inventory'+suffix+'.json'
        p = self.root/name
        p.write_text(json.dumps(inv))
        self.state['runs']['r1']['artifact_inventory'] = dict(reference=name,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(), inventory=inv)
        return inv

    def review(self):
        inv = self.state['runs']['r1']['artifact_inventory']
        r = a.draft_review('r1', inv['reference'], inv['inventory'])
        r.update(assessed_at=datetime.now(timezone.utc).isoformat(), reason='冗余中间checkpoint可再生',
                 preserve={k:['report.md'] for k in a.ROLES},
                 history=dict(related_run_ids=[], reason='没有替代旧实验', evidence=['report.md::来源检查']))
        for row in r['files']:
            row.update(decision='delete_candidate', reason='最终交付未使用此中间状态',
                evidence=['report.md::调用路径审查'], rebuild='按report.md入口重建',
                checks={key:dict(value=True, evidence=['report.md::依赖与重建核对'])
                        for key in ('no_future_use','no_protected_dependents','reproducible')})
        return r

    def register_review(self, review):
        path = self.root/'review.json'
        path.write_text(json.dumps(review))
        self.state['runs']['r1']['artifact_review'] = dict(reference='review.json', review=review,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            material_snapshots=a.material_snapshots(self.root, review))

    def test_success_can_retire_redundancy_but_protection_and_dependencies_win(self):
        r = self.review()
        self.assertEqual(a.validate_review(self.root,self.state,'r1',r), [])
        self.state['config']['artifact_policy'] = dict(a.DEFAULT_POLICY, protected_paths=['run'])
        self.inventory('protected'); r = self.review()
        self.assertIn('protected', ' '.join(a.validate_review(self.root,self.state,'r1',r)))
        self.state['config'] = {}
        self.inventory('consumer'); r=self.review()
        self.state['runs']['consumer'] = dict(artifact_inputs=[dict(path='run/middle.pt')])
        self.assertIn('dependency', ' '.join(a.validate_review(self.root,self.state,'r1',r)))

    def test_coverage_draft_and_changes_cannot_be_bypassed(self):
        r = self.review(); r['files']=[]
        self.assertIn('exactly all', ' '.join(a.validate_review(self.root,self.state,'r1',r)))
        draft = a.draft_review('r1','inventory.json', self.state['runs']['r1']['artifact_inventory']['inventory'])
        self.assertTrue(a.validate_review(self.root,self.state,'r1',draft))
        r=self.review(); self.binary.write_bytes(b'changed')
        self.assertIn('changed/missing', ' '.join(a.validate_review(self.root,self.state,'r1',r)))
        self.inventory('again'); r=self.review()
        (self.root/'run/new.mp4').write_bytes(b'new output')
        self.assertIn('unclassified', ' '.join(a.validate_review(self.root,self.state,'r1',r)))

    def test_reassessment_does_not_reset_seven_day_activity_clock(self):
        r=self.review()
        self.assertLess(a.utc(r['review_after']), datetime.now(timezone.utc))
        self.assertEqual(a.validate_review(self.root,self.state,'r1',r), [])
        self.state['runs']['r1']['updated_at']=datetime.now(timezone.utc).isoformat()
        # An immutable ended_at separates later narrative corrections from activity.
        self.state['runs']['r1']['ended_at']=self.old.isoformat()
        self.assertEqual(a.validate_review(self.root,self.state,'r1',r), [])

    def test_reusable_keep_requires_revisit_condition(self):
        r=self.review(); row=r['files'][0]
        row.update(decision='keep', keep_kind='reusable')
        self.assertIn('condition', ' '.join(a.validate_review(self.root,self.state,'r1',r)))
        row['review_condition']='保留给X对照；X结束后复评'
        self.assertEqual(a.validate_review(self.root,self.state,'r1',r), [])

    def test_hardlinks_symlinks_and_evidence_not_candidates(self):
        os.link(self.binary, self.root/'outside-alias.pt')
        (self.root/'run/link.pt').symlink_to(self.binary)
        self.inventory('links'); r=self.review()
        self.assertTrue(a.validate_review(self.root,self.state,'r1',r))
        self.binary.unlink(); (self.root/'outside-alias.pt').rename(self.binary)
        (self.root/'run/link.pt').unlink()
        self.inventory('evidence'); r=self.review()
        self.state['runs']['r1']['evidence']=[dict(reference='run/middle.pt')]
        self.assertIn('protected', ' '.join(a.validate_review(self.root,self.state,'r1',r)))

    def test_history_pending_blocks_closeout_and_requires_fresh_inventory(self):
        self.register_review(self.review())
        self.state['runs']['r2']=dict(status='completed', artifact_review_required=False)
        event=dict(event_id='evt-1', recorded_at=datetime.now(timezone.utc).isoformat())
        a.request_reassessments(self.state,'r2',['r1'],event)
        self.assertIn('history reassessment pending',' '.join(a.closeout_errors(self.root,self.state,['r2'])))
        self.assertIn('fresh inventory',' '.join(a.validate_review(self.root,self.state,'r1',self.review())))
        self.inventory('fresh'); self.register_review(self.review())
        task=self.state['artifact_reassessments']['r2::r1']; task['resolved_by']='evt-2'
        self.assertEqual(a.closeout_errors(self.root,self.state,['r2']), [])
        r=self.review(); r['history']['related_run_ids']=['r2']
        self.assertIn('earlier', ' '.join(a.validate_review(self.root,self.state,'r1',r)))

    def test_exact_cleanup_receipt_and_preserved_material_survive(self):
        r=self.review(); self.register_review(r)
        plan=a.make_cleanup_plan(self.root,self.state,['r1'])
        self.assertEqual(len(plan['files']),1)
        self.assertFalse(plan['deletion_authorized'])
        p=self.root/'plan.json'; p.write_text(json.dumps(plan))
        self.state['artifact_cleanup_plans']={'plan1':dict(plan=plan,reference='plan.json',
            sha256=hashlib.sha256(p.read_bytes()).hexdigest())}
        receipt=dict(plan_id='plan1',completed_at=datetime.now(timezone.utc).isoformat(),
            authorization_evidence=['report.md::用户授权清理精确清单'],
            verification_evidence=['report.md::保留材料与依赖已核对'],
            files=[dict(path='run/middle.pt',identity=plan['files'][0]['identity'],outcome='deleted',reason='已按清单删除')])
        with self.assertRaisesRegex(ValueError,'still exists'):
            validate_cleanup_result(self.root,self.state,receipt)
        self.binary.unlink()  # Isolated temporary fixture, no project cleanup.
        validate_cleanup_result(self.root,self.state,receipt)
        self.state['artifact_removed']={'run/middle.pt':dict(identity=plan['files'][0]['identity'])}
        self.assertEqual(a.closeout_errors(self.root,self.state,['r1']), [])
        self.assertEqual(a.make_cleanup_plan(self.root,self.state,['r1'])['files'],[])
        (self.root/'report.md').write_text('changed reproduction entry')
        self.assertIn('preserved', ' '.join(a.closeout_errors(self.root,self.state,['r1'])))

    def test_new_consumer_blocks_cleanup_and_receipt(self):
        self.register_review(self.review())
        self.state['runs']['r2']=dict(status='running',artifact_inputs=[dict(path=str(self.binary))])
        with self.assertRaisesRegex(ValueError,'protected'):
            a.make_cleanup_plan(self.root,self.state,['r1'])

    def test_legacy_replay_does_not_gain_new_fields(self):
        state=dict(runs={'old':dict(status='running', evidence=[], updated_at='old')})
        result=apply_event(state,dict(event_type='run_status_changed',event_id='evt-1',sequence=1,
            event_hash='h',recorded_at='2026-01-01T00:00:00+00:00',
            payload=dict(run_id='old',status='completed',summary='done',evidence=[])))
        self.assertNotIn('ended_at',result['runs']['old'])


if __name__ == '__main__': unittest.main()

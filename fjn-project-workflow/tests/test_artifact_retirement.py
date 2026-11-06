"""Scoped user retirement must not weaken unrelated artifact protection."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,hashlib,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_artifact_inventory import InventoryTests
import artifact_inventory as a
import artifact_retirement as retire
from artifact_commands import validate_cleanup_result
from workflow_core import apply_event

class RetirementTests(InventoryTests):
    def authorize(self,scope=None):
        v=dict(schema_version=1,run_ids=scope or ['r1'],waive_recent_protection=True,
            authorization_evidence=['report.md::User explicitly retires exact assets now'],reason='User override for terminal study only',
            files=[dict(path='run/middle.pt',identity=a.identity(self.binary))])
        retire.validate(self.root,self.state,v)
        self.state['artifact_retirements']={'a1':dict(authorization=v)}
        return v

    def test_recent_authorized_plan_and_receipt(self):
        t=datetime.now(timezone.utc).timestamp();os.utime(self.binary,(t,t));self.inventory('recent')
        self.state['runs']['r2']=dict(status='completed',artifact_inputs=[dict(path='run')],artifact_inventory={})
        self.authorize(['r1','r2']);r=self.review();self.assertEqual(a.validate_review(self.root,self.state,'r1',r),[])
        self.register_review(r);p=a.make_cleanup_plan(self.root,self.state,['r1']);self.assertEqual(len(p['files']),1)
        self.assertGreater(a.utc(r['review_after']),datetime.now(timezone.utc))
        q=self.root/'plan.json';q.write_text(json.dumps(p));self.state['artifact_cleanup_plans']={'p1':dict(reference='plan.json',sha256=hashlib.sha256(q.read_bytes()).hexdigest(),plan=p)}
        self.state['config']['artifact_policy']=dict(a.DEFAULT_POLICY, protected_paths=['unrelated-new-mainline'])
        row=p['files'][0];self.binary.unlink();receipt=dict(plan_id='p1',completed_at=datetime.now(timezone.utc).isoformat(),authorization_evidence=['report.md::Explicit retirement'],verification_evidence=['report.md::Exact preflight'],files=[dict(path=row['path'],identity=row['identity'],outcome='deleted',reason='Retired')])
        validate_cleanup_result(self.root,self.state,receipt)
        self.state.setdefault('artifact_removed',{})[row['path']]=dict(identity=row['identity'])
        self.assertEqual(a.closeout_errors(self.root,self.state,['r1']),[])

    def test_no_waiver_keeps_recent_plan_empty(self):
        t=datetime.now(timezone.utc).timestamp();os.utime(self.binary,(t,t));self.inventory('recent');self.register_review(self.review())
        self.assertEqual(a.make_cleanup_plan(self.root,self.state,['r1'])['files'],[])

    def test_external_or_active_consumer_blocks(self):
        self.state['runs']['external']=dict(status='completed',artifact_inputs=[dict(path='run')])
        with self.assertRaisesRegex(ValueError,'external consumer'):self.authorize()
        self.state['runs'].pop('external');self.state['runs']['r1']['status']='running'
        with self.assertRaisesRegex(ValueError,'active'):self.authorize()

    def test_terminal_internal_consumer_and_later_external_revocation(self):
        self.state['runs']['r2']=dict(status='completed',artifact_inputs=[dict(path='run')],artifact_inventory={})
        self.authorize(['r1','r2']);self.assertFalse(a.protected(self.binary,a.protected_paths(self.root,self.state)))
        self.state['runs']['r3']=dict(status='running',artifact_inputs=[dict(path='run')])
        self.assertTrue(a.protected(self.binary,a.protected_paths(self.root,self.state)))

    def test_hard_package_evidence_shared_and_changed_identity_block(self):
        self.state['config']['artifact_policy']=dict(a.DEFAULT_POLICY,protected_paths=['run'])
        with self.assertRaisesRegex(ValueError,'protected'):self.authorize()
        self.state['config']={};self.authorize();self.binary.write_bytes(b'new generation')
        self.assertNotIn(self.binary,retire.allowed_paths(self.root,self.state))

    def test_new_preserve_cannot_be_waived(self):
        self.authorize();r=self.review();r['preserve']['inputs']=['run/middle.pt']
        self.assertIn('protected',' '.join(a.validate_review(self.root,self.state,'r1',r)))

    def test_legacy_preserve_list_remains_hard(self):
        self.state['runs']['legacy']=dict(status='completed',artifact_review=dict(reference='report.md',review=dict(schema_version=1,preserve=['report.md'])))
        self.authorize()
        self.state['runs']['legacy']['artifact_review']['review']['preserve']=['run/middle.pt']
        with self.assertRaisesRegex(ValueError,'preserved'):self.authorize()

    def test_old_receipt_does_not_authorize_recreated_file(self):
        v=self.authorize();self.state['artifact_removed']={'run/middle.pt':dict(identity=v['files'][0]['identity'])}
        self.binary.unlink();self.binary.write_bytes(b'a new generation must not inherit old user exception')
        self.assertNotIn(self.binary,retire.allowed_paths(self.root,self.state))

    def test_skipped_receipt_accepts_native_full_inventory_identity(self):
        self.register_review(self.review());plan=a.make_cleanup_plan(self.root,self.state,['r1'])
        p=self.root/'plan.json';p.write_text(json.dumps(plan));self.state['artifact_cleanup_plans']={'p1':dict(reference='plan.json',sha256=hashlib.sha256(p.read_bytes()).hexdigest(),plan=plan)}
        row=plan['files'][0];receipt=dict(plan_id='p1',completed_at=datetime.now(timezone.utc).isoformat(),authorization_evidence=['report.md::Authorization'],verification_evidence=['report.md::Intentionally skipped'],files=[dict(path=row['path'],identity=row['identity'],outcome='skipped',reason='Retain original file')])
        validate_cleanup_result(self.root,self.state,receipt)

    def test_additive_protection_still_blocks_newly_protected_asset(self):
        self.authorize();r=self.review();self.register_review(r)
        self.state['config']['artifact_policy']=dict(a.DEFAULT_POLICY,protected_paths=['run'])
        self.assertTrue(a.policy_compatible(a.DEFAULT_POLICY,a.policy(self.state)))
        self.assertIn('protected',' '.join(a.validate_review(self.root,self.state,'r1',r)))

    def test_policy_removal_or_selection_change_is_not_compatible(self):
        self.assertFalse(a.policy_compatible(dict(a.DEFAULT_POLICY,protected_paths=['run']),a.DEFAULT_POLICY))
        self.assertFalse(a.policy_compatible(a.DEFAULT_POLICY,dict(a.DEFAULT_POLICY,recent_days=8)))
        self.assertFalse(a.policy_compatible(a.DEFAULT_POLICY,dict(a.DEFAULT_POLICY,min_size_bytes=1)))

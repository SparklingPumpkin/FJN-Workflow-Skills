"""Workflow CLI handlers for inventories, scoped reassessment and cleanup records.

No command in this module deletes experiment assets.
"""
from __future__ import annotations

import json
from pathlib import Path

import artifact_inventory as a
from artifact_review import local_file
import workflow_core as w


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def read(root, name):
    return w.read_json(local_file(root, name))


def write_new(root, name, value):
    path = w.project_path(root, name)
    if Path(name).is_absolute() or not path.parent.is_dir() or path.exists() or path.is_symlink():
        raise ValueError('output must be a new project-relative file in an existing directory')
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return dict(reference=name, sha256=w.sha256_file(path))


def command(args):
    root = Path(args.project_root).resolve()
    try:
        with w.exclusive_lock(root, args.control_dir):
            state, _ = w.load_and_verify(root, args.control_dir)
            action = args.command
            if action == 'authorize-artifact-retirement':
                from artifact_retirement import validate
                value = read(root, args.authorization_file)
                validate(root, state, value)
                record = dict(reference=args.authorization_file, sha256=w.sha256_file(root/args.authorization_file), authorization=value)
                _, event = w.append_event_and_render(root, args.control_dir, 'artifact_retirement_authorized', dict(record=record))
                output(dict(event_id=event['event_id'], files=len(value['files']), deletion_executed=False))
            elif action == 'set-artifact-policy':
                value = read(root, args.policy_file)
                a.validate_policy(value)
                evidence = w.parse_evidence(root, args.evidence)
                if not args.reason.strip(): raise ValueError('policy change needs reason')
                _, event = w.append_event_and_render(root, args.control_dir, 'artifact_policy_recorded',
                    dict(policy=value, reason=args.reason, evidence=evidence))
                output(dict(event_id=event['event_id'], policy=value, deletion_executed=False))
            elif action == 'scan-artifacts':
                inventory = a.scan(root, state, args.run_id)
                # Inventory/review outputs must not classify themselves as generated run assets.
                base = a.run_directory(root, state, args.run_id)
                if w.project_path(root, args.output).is_relative_to(base.resolve()):
                    raise ValueError('write inventory outside the run directory (e.g. control directory)')
                record = write_new(root, args.output, inventory)
                record['inventory'] = inventory
                _, event = w.append_event_and_render(root, args.control_dir, 'artifact_inventory_recorded',
                                                      dict(run_id=args.run_id, record=record))
                output(dict(event_id=event['event_id'], inventory_reference=args.output,
                            file_count=len(inventory['files']),
                            review_draft=a.draft_review(args.run_id, args.output, inventory)))
            elif action == 'request-artifact-reassessment':
                source = state['runs'][args.source_run_id]
                targets = args.run_id
                order = list(state['runs'])
                if source['status'] not in a.TERMINAL:
                    raise ValueError('request after source run is terminal')
                if any(x not in order or order.index(x) >= order.index(args.source_run_id) for x in targets):
                    raise ValueError('targets must be earlier registered runs')
                evidence = w.parse_evidence(root, args.evidence)
                if not args.reason.strip(): raise ValueError('reassessment needs a concrete reason')
                _, event = w.append_event_and_render(root, args.control_dir, 'artifact_reassessment_requested',
                    dict(source_run_id=args.source_run_id, target_run_ids=targets,
                         reason=args.reason, evidence=evidence))
                output(dict(event_id=event['event_id'], deletion_executed=False))
            elif action == 'check-artifact-closeout':
                errors = a.closeout_errors(root, state, args.run_id)
                if errors: raise ValueError('; '.join(errors))
                output(dict(passed=True, run_ids=args.run_id))
            elif action == 'artifact-review-due':
                rows = []
                now = a.datetime.now(a.timezone.utc)
                for rid, run in state['runs'].items():
                    review = run.get('artifact_review', {}).get('review')
                    if not review: continue
                    if a.utc(review['review_after']) <= now:
                        rows.append(dict(run_id=rid, review=run['artifact_review']['reference'],
                            decision=review.get('decision', 'file_level'),
                            cleanup_candidates=sum((x.get('decision', review.get('decision')) == 'delete_candidate')
                                and x['path'] not in state.get('artifact_removed', {}) for x in review['files'])))
                output(dict(due=rows, pending_history=[t for t in state.get('artifact_reassessments', {}).values()
                            if not t.get('resolved_by')], deletion_executed=False))
            elif action == 'plan-artifact-cleanup':
                plan = a.make_cleanup_plan(root, state, args.run_id)
                record = write_new(root, args.output, plan)
                record['plan'] = plan
                _, event = w.append_event_and_render(root, args.control_dir, 'artifact_cleanup_planned', dict(record=record))
                output(dict(plan_id=event['event_id'], reference=args.output,
                            expected_released_bytes=plan['expected_released_bytes'],
                            file_count=len(plan['files']), skipped=plan['skipped'], deletion_executed=False))
            elif action == 'record-artifact-cleanup':
                result = read(root, args.result_file)
                validate_cleanup_result(root, state, result)
                record = dict(reference=args.result_file, sha256=w.sha256_file(root/args.result_file))
                _, event = w.append_event_and_render(root, args.control_dir, 'artifact_cleanup_recorded',
                                                      dict(result=result, record=record))
                output(dict(event_id=event['event_id'], deletion_executed=False,
                            note='Records externally performed cleanup; does not itself delete files'))
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        raise w.WorkflowError(str(exc)) from exc


def validate_cleanup_result(root, state, result):
    """Record missing files only against exact original plan; never amend history."""
    plan_id = result['plan_id']
    record = state.get('artifact_cleanup_plans', {}).get(plan_id)
    if not record: raise ValueError('unknown cleanup plan')
    if any(x['result']['plan_id'] == plan_id for x in state.get('artifact_cleanup_results', {}).values()):
        raise ValueError('cleanup plan already has a receipt')
    if w.sha256_file(root/record['reference']) != record['sha256']:
        raise ValueError('cleanup plan changed')
    plan = record['plan']
    completed = a.utc(result['completed_at'])
    if completed < a.utc(plan['created_at']) or completed > a.datetime.now(a.timezone.utc)+a.timedelta(minutes=5):
        raise ValueError('cleanup completion timestamp invalid')
    a.evidence(root, result.get('authorization_evidence'))
    a.evidence(root, result.get('verification_evidence'))
    rows = result['files']
    expected = {x['path']: x for x in plan['files']}
    if len(rows) != len(expected) or {x['path'] for x in rows} != set(expected):
        raise ValueError('receipt must cover exact plan paths once, including skipped files')
    # Validate retained material on the projected post-cleanup state, allowing
    # only these exact missing paths. Existing new dependencies still block.
    from copy import deepcopy
    after = deepcopy(state)
    # Exact planned deletions establish the projected identity for scoped retirement
    # while existence, consumer and receipt checks below still apply.
    for row in rows:
        if row.get('outcome') == 'deleted' and row.get('identity') == expected[row['path']]['identity']:
            after.setdefault('artifact_removed', {})[row['path']] = dict(identity=row['identity'])
    guards = a.protected_paths(root, after)
    if not a.policy_compatible(plan['policy'], a.policy(state)): raise ValueError('policy changed since cleanup plan')
    for rid, sha in plan['review_references'].items():
        if state['runs'][rid]['artifact_review']['sha256'] != sha:
            raise ValueError('review changed since plan; replan')
    for row in rows:
        path = root/row['path']; prior = expected[row['path']]['identity']
        if row.get('identity') != prior or not row.get('reason', '').strip():
            raise ValueError('receipt must carry original file identity and outcome reason')
        if row['outcome'] == 'deleted':
            if path.exists() or path.is_symlink(): raise ValueError('deleted path still exists')
            if a.protected(path, guards): raise ValueError('new protected dependency was deleted; restore before recording')
            after.setdefault('artifact_removed', {})[row['path']] = dict(identity=prior)
        elif row['outcome'] == 'skipped':
            if a.identity(path) != {k:v for k,v in prior.items() if k != 'path'}: raise ValueError('skipped file changed')
        else: raise ValueError('outcome must be deleted or skipped')
    errors = a.closeout_errors(root, after, list(plan['review_references']))
    if errors: raise ValueError('; '.join(errors))


def add_commands(sub, add_common):
    p = sub.add_parser('authorize-artifact-retirement', help='Record explicit user scoped exact-file retirement; preserves hard/external protections')
    add_common(p); p.add_argument('--authorization-file', required=True); p.set_defaults(func=command)
    p = sub.add_parser('set-artifact-policy', help='Record thresholds/recent protection/exact protected paths; never delete')
    add_common(p); p.add_argument('--policy-file', required=True); p.add_argument('--reason', required=True)
    p.add_argument('--evidence', action='append', required=True); p.set_defaults(func=command)
    p = sub.add_parser('scan-artifacts', help='Inventory a terminal run and print an intentionally incomplete v2 review draft')
    add_common(p); p.add_argument('--run-id', required=True); p.add_argument('--output', required=True); p.set_defaults(func=command)
    p = sub.add_parser('request-artifact-reassessment', help='Append scoped requests after changed conclusions/replacement')
    add_common(p); p.add_argument('--source-run-id', required=True); p.add_argument('--run-id', action='append', required=True)
    p.add_argument('--reason', required=True); p.add_argument('--evidence', action='append', required=True); p.set_defaults(func=command)
    for name, help_text in [('check-artifact-closeout', 'Hard scoped finalization gate, repair/termination writes remain available'),
                            ('plan-artifact-cleanup', 'Export exact eligible file plan; no authorization or deletion')]:
        p = sub.add_parser(name, help=help_text); add_common(p)
        p.add_argument('--run-id', action='append', required=True)
        if name == 'plan-artifact-cleanup': p.add_argument('--output', required=True)
        p.set_defaults(func=command)
    p = sub.add_parser('artifact-review-due', help='List due assessments and unresolved history requests')
    add_common(p); p.set_defaults(func=command)
    p = sub.add_parser('record-artifact-cleanup', help='Record and verify externally performed cleanup; never deletes')
    add_common(p); p.add_argument('--result-file', required=True); p.set_defaults(func=command)

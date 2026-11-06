"""File-level artifact assessments and exact cleanup plans. Never unlink files.

Inventories and reviews live in the existing workflow ledger. Machine checks
enforce coverage and known protection, not the truth of scientific judgments.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

from artifact_review import DECISIONS, TERMINAL, local_file, utc

MEDIA = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.png', '.jpg', '.jpeg', '.webp', '.exr', '.gif'}
GENERATED = {'.pt', '.pth', '.ckpt', '.safetensors', '.ply', '.npy', '.npz', '.bin', '.pkl', '.pickle'}
DEFAULT_POLICY = dict(min_size_bytes=64*1024**2, recent_days=7, protected_paths=[])
ROLES = {'conclusion', 'metrics_timing', 'reproduction', 'code_identity', 'inputs'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def policy(state):
    return dict(DEFAULT_POLICY, **state.get('config', {}).get('artifact_policy', {}))


def policy_compatible(old, current):
    # Additive protection cannot permit any new deletion. Current exact-path
    # protection is still checked by review/plan/receipt; selection and recency
    # changes or protection removal require a fresh inventory/plan.
    return (old.get('min_size_bytes') == current.get('min_size_bytes')
            and old.get('recent_days') == current.get('recent_days')
            and set(old.get('protected_paths', [])) <= set(current.get('protected_paths', [])))


def validate_policy(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT_POLICY):
        raise ValueError('policy must contain min_size_bytes, recent_days, protected_paths')
    if type(value['min_size_bytes']) is not int or value['min_size_bytes'] < 1:
        raise ValueError('min_size_bytes must be a positive integer')
    if type(value['recent_days']) is not int or value['recent_days'] < 7:
        raise ValueError('recent_days must be at least seven')
    if not isinstance(value['protected_paths'], list):
        raise ValueError('protected_paths must be a list of exact paths (no globs)')
    for p in value['protected_paths']:
        if not isinstance(p, str) or not p or any(x in p for x in '*?[]') or '..' in Path(p).parts:
            raise ValueError('protected_paths must be exact paths without traversal/globs')


def run_directory(root, state, run_id):
    run = state['runs'][run_id]
    directory = state['directories'][run['directory_id']]['path']
    result = root / directory
    if result.is_symlink() or not result.resolve().is_relative_to(root.resolve()) or not result.is_dir():
        raise ValueError('run directory must be an existing directory inside the project')
    return result


def identity(path):
    s = path.lstat()
    out = dict(size_bytes=s.st_size, mtime_ns=s.st_mtime_ns, device=s.st_dev,
               inode=s.st_ino, nlink=s.st_nlink, mode=s.st_mode, allocated_bytes=s.st_blocks*512)
    if stat.S_ISLNK(s.st_mode):
        out['link_target'] = os.readlink(path)
    return out


def exact_path(root, value):
    if not isinstance(value, str) or not value or any(c in value for c in '*?[]') or '..' in Path(value).parts:
        raise ValueError('expected exact path without globs/traversal')
    p = Path(value)
    return p if p.is_absolute() else root / p


def evidence(root, entries):
    if not isinstance(entries, list) or not entries:
        raise ValueError('evidence must contain local-file::claim entries')
    for entry in entries:
        if not isinstance(entry, str) or '::' not in entry:
            raise ValueError('evidence must use local-file::claim')
        ref, claim = entry.split('::', 1)
        if not claim.strip():
            raise ValueError('evidence claim must be nonempty')
        local_file(root, ref)


class ProtectedPaths(set):
    pass


def protected_paths(root, state):
    """Conservative known references. Does not claim to discover all loads."""
    from functools import lru_cache
    @lru_cache(maxsize=None)
    def resolved(value):
        return exact_path(root, value).resolve()
    paths = ProtectedPaths(resolved(x) for x in policy(state)['protected_paths'])
    paths.hard = set(paths)
    from artifact_retirement import allowed_paths
    paths.retired = allowed_paths(root, state)
    def visit(value):
        if isinstance(value, dict):
            ref = value.get('reference')
            if isinstance(ref, str) and '://' not in ref and not ref.startswith(('user:', 'external:')):
                paths.add(resolved(ref))
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    for collection in ('runs', 'candidates', 'versions'):
        for item in state.get(collection, {}).values():
            visit(item.get('evidence', []))
            visit(item.get('acceptance_contract', {}))
            visit(item.get('acceptance_report', {}))
    paths.hard.update(paths)
    for run in state.get('runs', {}).values():
        for item in run.get('artifact_inputs', []):
            paths.add(resolved(item['path']))
        review = run.get('artifact_review', {}).get('review', {})
        if review.get('schema_version') == 2:
            material = {resolved(p) for p in review_evidence_files(review)}
            paths.update(material); paths.hard.update(material)
            for group in review.get('preserve', {}).values():
                material = {resolved(p) for p in group}
                paths.update(material); paths.hard.update(material)
            for row in review.get('files', []):
                if row['decision'] == 'keep' and row.get('keep_kind') in {'evidence', 'dependency', 'protected'}:
                    paths.add(resolved(row['path']))
        for key in ('artifact_inventory', 'artifact_review'):
            if run.get(key): paths.add(resolved(run[key]['reference']))
    return paths


def review_evidence_files(review):
    result = set()
    def visit(value):
        if isinstance(value, dict):
            for entry in value.get('evidence', []):
                if isinstance(entry, str) and '::' in entry: result.add(entry.split('::', 1)[0])
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(review)
    return result


def material_snapshots(root, review):
    paths = review_evidence_files(review)
    paths.update(p for group in review['preserve'].values() for p in group)
    rows = {}
    for name in sorted(paths):
        path = local_file(root, name)
        row = identity(path)
        if row['size_bytes'] <= 10*1024**2:
            row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows[name] = row
    return rows


def protected(path, paths):
    resolved = path.resolve()
    ancestors = (resolved, *resolved.parents)
    if any(p in getattr(paths, 'hard', set()) for p in ancestors):
        return True
    if resolved in getattr(paths, 'retired', set()):
        return False
    return any(p in paths for p in ancestors)


def scan(root, state, run_id):
    run = state['runs'][run_id]
    if run['status'] not in TERMINAL:
        raise ValueError('scan requires a terminal run; recording termination stays available')
    base = run_directory(root, state, run_id)
    settings = policy(state)
    validate_policy(settings)
    files = []
    latest = utc(run.get('ended_at', run['updated_at']))
    for directory, dirs, names in os.walk(base, followlinks=False):
        for name in list(dirs):
            p = Path(directory) / name
            if p.is_symlink():
                names.append(name); dirs.remove(name)
            elif name in {'.git', '__pycache__', '.pytest_cache'}:
                dirs.remove(name)
        for name in sorted(names):
            p = Path(directory) / name
            s = identity(p)
            selected = (stat.S_ISLNK(s['mode']) or p.suffix.lower() in MEDIA | GENERATED
                        or s['size_bytes'] >= settings['min_size_bytes'])
            if selected:
                files.append(dict(path=p.relative_to(root).as_posix(), **s))
            if selected or p.suffix.lower() == '.log' or p.name in {'pipeline_timing.json', 'result_summary.json'}:
                latest = max(latest, datetime.fromtimestamp(s['mtime_ns']/1e9, timezone.utc))
    return dict(schema_version=2, run_id=run_id, scanned_at=datetime.now(timezone.utc).isoformat(),
                policy=settings, last_activity_at=latest.isoformat(), files=sorted(files, key=lambda x:x['path']))


def scan_errors(root, state, run_id, inventory):
    """Rescan closeout scope; receipts account only for exact recorded removals."""
    current = scan(root, state, run_id)
    errors = []
    if not policy_compatible(inventory['policy'], current['policy']):
        errors.append('artifact policy changed; rescan and reassess')
    actual = {x['path']: x for x in current['files']}
    expected = {x['path']: x for x in inventory['files']}
    removed = state.get('artifact_removed', {})
    for path, old in expected.items():
        if path in removed and removed[path]['identity'] == old and path not in actual:
            continue
        if actual.get(path) != old:
            errors.append(f'artifact changed/missing: {path}; rescan or record cleanup receipt')
    for path in actual.keys() - expected.keys():
        errors.append(f'unclassified artifact: {path}; rescan and reassess')
    # New numerical logs/activity invalidate an old scan even without a new payload.
    if utc(current['last_activity_at']) > utc(inventory['last_activity_at']):
        errors.append('new experiment activity after inventory; rescan and reassess')
    return errors


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def request_reassessments(state, source, targets, event, only_new=False):
    tasks = state.setdefault('artifact_reassessments', {})
    for target in targets:
        if state['runs'][target]['status'] not in TERMINAL:
            continue  # Active inputs remain protected, not forced into a terminal assessment.
        key = source + '::' + target
        if only_new and key in tasks: continue
        tasks[key] = dict(source_run_id=source, target_run_id=target,
                          requested_at=event['recorded_at'], requested_event=event['event_id'])


def validate_review(root, state, run_id, review):
    try:
        _validate_review(root, state, run_id, review)
        return []
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        return [str(exc)]


def _validate_review(root, state, run_id, review):
    run = state['runs'][run_id]
    if run['status'] not in TERMINAL or review.get('run_id') != run_id:
        raise ValueError('v2 review requires matching terminal run')
    record = run.get('artifact_inventory')
    if not record or review.get('inventory_reference') != record['reference']:
        raise ValueError('review must reference the latest tool-generated registered inventory')
    inv = record['inventory']
    errors = scan_errors(root, state, run_id, inv)
    if errors: raise ValueError('; '.join(errors))
    assessed = utc(review['assessed_at'])
    if assessed < utc(inv['scanned_at']) or assessed > datetime.now(timezone.utc)+timedelta(minutes=5):
        raise ValueError('assessment must follow inventory scan and not be in the future')
    for task in state.get('artifact_reassessments', {}).values():
        if task['target_run_id'] == run_id and not task.get('resolved_by') and utc(inv['scanned_at']) < utc(task['requested_at']):
            raise ValueError('historical reassessment needs a fresh inventory after request')
    # Reviewing an old run does not reset its activity-based protection clock.
    eligible = utc(inv['last_activity_at'])+timedelta(days=inv['policy']['recent_days'])
    if utc(review['review_after']) < eligible:
        raise ValueError('review_after must respect last experimental activity plus recent_days')
    if not nonempty(review.get('reason')):
        raise ValueError('review needs a substantive reason')
    preserve = review.get('preserve')
    if not isinstance(preserve, dict) or set(preserve) != ROLES:
        raise ValueError('preserve must cover conclusion, metrics_timing, reproduction, code_identity, inputs')
    for group in preserve.values():
        if not isinstance(group, list) or not group: raise ValueError('each preserve role needs actual files')
        for path in group: local_file(root, path)
    history = review.get('history', {})
    related = history.get('related_run_ids')
    if not isinstance(related, list) or len(set(related)) != len(related):
        raise ValueError('history.related_run_ids must explicitly list unique related old runs (or [])')
    if not set(run.get('artifact_related_runs', [])).issubset(related):
        raise ValueError('history omits declared related runs')
    evidence(root, history.get('evidence'))
    if not nonempty(history.get('reason')): raise ValueError('history needs reason, including explicit none')
    for target in related:
        if target not in state['runs'] or list(state['runs']).index(target) >= list(state['runs']).index(run_id):
            raise ValueError('history target must be an earlier registered run; no cycles or inferred ancestry')
    rows = review.get('files')
    if not isinstance(rows, list): raise ValueError('files must classify the entire inventory')
    invrows = {x['path']: x for x in inv['files']}
    if len(rows) != len(invrows) or {x['path'] for x in rows} != set(invrows):
        raise ValueError('files must classify exactly all inventory entries, without omission/duplicates')
    # Ignore this run's previous decisions: a new assessment may retire a former keep.
    from copy import deepcopy
    view = deepcopy(state)
    view['runs'][run_id].pop('artifact_review', None)
    protected_set = protected_paths(root, view)
    retained = {(root/p).resolve() for group in preserve.values() for p in group}
    retained.update((root/p).resolve() for p in review_evidence_files(review))
    protected_set.update(retained)
    protected_set.hard.update(retained)
    for row in rows:
        path = row['path']; p = root/path; info = invrows[path]
        if row.get('decision') not in DECISIONS or not nonempty(row.get('reason')):
            raise ValueError(f'{path}: needs decision and substantive reason')
        evidence(root, row.get('evidence'))
        if row['decision'] == 'keep':
            kind = row.get('keep_kind')
            if kind not in {'evidence', 'dependency', 'protected', 'reusable'}:
                raise ValueError(f'{path}: keep_kind must identify actual value/protection')
            if kind == 'dependency':
                consumers = row.get('consumer_run_ids', [])
                if not consumers or any(x not in state['runs'] for x in consumers):
                    raise ValueError(f'{path}: dependency keep needs registered consumers')
            if kind == 'reusable' and not nonempty(row.get('review_condition')):
                raise ValueError(f'{path}: reusable keep needs concrete purpose and reassessment condition')
        elif row['decision'] == 'needs_review':
            if not nonempty(row.get('review_condition')):
                raise ValueError(f'{path}: needs_review must state unresolved question and revisit condition')
        else:
            if protected(p, protected_set) or info['nlink'] > 1 or not stat.S_ISREG(info['mode']):
                raise ValueError(f'{path}: protected/evidence/dependency/shared/symlink cannot be deletion candidate')
            if not nonempty(row.get('rebuild')):
                raise ValueError(f'{path}: deletion candidate needs reconstruction entry/instructions')
            checks = row.get('checks', {})
            if set(checks) != {'no_future_use', 'no_protected_dependents', 'reproducible'}:
                raise ValueError(f'{path}: deletion candidate needs three evidence-backed checks')
            for item in checks.values():
                if item.get('value') is not True: raise ValueError(f'{path}: uncertain eligibility stays needs_review')
                evidence(root, item.get('evidence'))


def closeout_errors(root, state, run_ids):
    """Scoped hard gate; never used by the ledger write/repair preflight."""
    errors = []
    from artifact_review import validate_artifact_review
    selected = set(run_ids)
    # Follow only explicit reassessment work, never all historical ancestors.
    changed = True
    while changed:
        before = set(selected)
        selected.update(t['target_run_id'] for t in state.get('artifact_reassessments', {}).values()
                        if t['source_run_id'] in selected)
        changed = selected != before
    for rid in sorted(selected):
        run = state['runs'].get(rid, {})
        if run.get('status') not in TERMINAL:
            errors.append(f'{rid}: run not terminal'); continue
        record = run.get('artifact_review')
        if not record:
            if run.get('artifact_review_required'): errors.append(f'{rid}: artifact review missing')
            continue
        if run.get('artifact_review_schema', 1) == 2 and record['review'].get('schema_version') != 2:
            errors.append(f'{rid}: new run requires file-level schema v2'); continue
        source = root/record['reference']
        if not source.is_file() or (record.get('sha256') and hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']):
            errors.append(f'{rid}: artifact review file changed/missing'); continue
        inventory = run.get('artifact_inventory')
        if record['review'].get('schema_version') == 2:
            invsource = root/inventory['reference']
            if not invsource.is_file() or hashlib.sha256(invsource.read_bytes()).hexdigest() != inventory['sha256']:
                errors.append(f'{rid}: inventory changed/missing'); continue
            try:
                if material_snapshots(root, record['review']) != record.get('material_snapshots'):
                    errors.append(f'{rid}: preserved evidence/reproducer changed; append fresh review')
            except (OSError, ValueError) as exc:
                errors.append(f'{rid}: preserved evidence/reproducer missing: {exc}')
        errors.extend(f'{rid}: {e}' for e in validate_artifact_review(root, state, rid, record['review']))
    for task in state.get('artifact_reassessments', {}).values():
        if (task['source_run_id'] in selected or task['target_run_id'] in selected) and not task.get('resolved_by'):
            errors.append(f"history reassessment pending: {task['source_run_id']} -> {task['target_run_id']}")
    return errors


def draft_review(run_id, reference, inventory):
    """Draft intentionally cannot pass: an agent must supply concrete evidence."""
    return dict(schema_version=2, run_id=run_id, inventory_reference=reference,
        assessed_at=None, review_after=(utc(inventory['last_activity_at'])+timedelta(days=inventory['policy']['recent_days'])).isoformat(),
        reason='', preserve={key: [] for key in sorted(ROLES)},
        history=dict(related_run_ids=[], reason='', evidence=[]),
        files=[dict(path=f['path'], decision='needs_review', reason='', review_condition='', evidence=[]) for f in inventory['files']])


def make_cleanup_plan(root, state, run_ids, now=None):
    now = now or datetime.now(timezone.utc)
    errors = closeout_errors(root, state, run_ids)
    if errors: raise ValueError('; '.join(errors))
    plan = dict(schema_version=2, created_at=now.isoformat(), deletion_authorized=False,
                policy=policy(state), files=[], skipped=[], review_references={},
                warning='Known-dependency checks are incomplete without inspecting actual loaders and live activity. No deletion is performed.')
    guards = protected_paths(root, state)
    for rid in sorted(set(run_ids)):
        run = state['runs'][rid]
        review_record = run.get('artifact_review', {})
        review = review_record.get('review', {})
        if review.get('schema_version') != 2: raise ValueError('cleanup export requires v2 review; legacy evidence remains intact')
        inv = run['artifact_inventory']['inventory']
        plan['review_references'][rid] = review_record['sha256']
        info = {x['path']: x for x in inv['files']}
        for row in review['files']:
            if row['decision'] != 'delete_candidate' or row['path'] in state.get('artifact_removed', {}): continue
            path = root/row['path']
            why = None
            if now < utc(review['review_after']) and path.resolve() not in getattr(guards, 'retired', set()): why = 'recent protection/review date not reached'
            elif protected(path, guards): why = 'new protection or declared consumer'
            if why:
                plan['skipped'].append(dict(path=row['path'], reason=why)); continue
            plan['files'].append(dict(path=row['path'], run_id=rid, identity=info[row['path']],
                                      reason=row['reason'], rebuild=row['rebuild']))
    plan['expected_released_bytes'] = sum(x['identity']['allocated_bytes'] for x in plan['files'])
    return plan

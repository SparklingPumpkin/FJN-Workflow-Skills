"""Explicit, exact-file retirement exceptions; never grants deletion itself."""
from pathlib import Path
import stat


def allowed_paths(root, state):
    result = set()
    for record in state.get('artifact_retirements', {}).values():
        value = record['authorization']
        scope = set(value['run_ids'])
        if any(state['runs'].get(rid, {}).get('status') not in {'completed','failed','cancelled'} for rid in scope):
            continue
        candidates = {(root / row['path']).resolve(): row for row in value['files']}
        # Any consumer outside the explicitly retired terminal set revokes its waiver.
        external = set()
        for rid, run in state.get('runs', {}).items():
            if rid in scope:
                continue
            for item in run.get('artifact_inputs', []):
                q = Path(item['path']); external.add((q if q.is_absolute() else root/q).resolve())
        candidates = {p:row for p,row in candidates.items()
                      if not any(parent in external for parent in (p, *p.parents))}
        for p, row in candidates.items():
            removed = state.get('artifact_removed', {}).get(row['path'])
            if p.exists() or p.is_symlink():
                from artifact_inventory import identity
                if p.is_file() and not p.is_symlink() and identity(p) == row['identity']:
                    result.add(p)
            elif removed and {k:v for k,v in removed['identity'].items() if k != 'path'} == row['identity']:
                result.add(p)
    return result


def validate(root, state, value):
    from artifact_inventory import evidence, identity, policy, exact_path, TERMINAL
    if value.get('schema_version') != 1 or value.get('waive_recent_protection') is not True:
        raise ValueError('retirement requires explicit scoped recent-protection waiver')
    evidence(root, value.get('authorization_evidence'))
    if not value.get('reason', '').strip():
        raise ValueError('explicit retirement needs reason')
    scope = value.get('run_ids', [])
    if not scope or len(set(scope)) != len(scope):
        raise ValueError('retirement must name unique terminal runs')
    for rid in scope:
        if state['runs'].get(rid, {}).get('status') not in TERMINAL:
            raise ValueError('retirement scope includes active/unknown run')
    # Hard protections survive user retirement of temporary diagnostic results.
    from copy import deepcopy
    from artifact_inventory import protected_paths, protected
    view = deepcopy(state)
    for rid in scope:
        view['runs'][rid].pop('artifact_review', None)
        view['runs'][rid]['artifact_inputs'] = []
    view['artifact_retirements'] = {}
    hard = protected_paths(root, view)
    rows = value.get('files', [])
    if not rows or len({x['path'] for x in rows}) != len(rows):
        raise ValueError('retirement needs unique exact file identities')
    inventory = {}
    for rid in scope:
        for item in state['runs'][rid].get('artifact_inventory', {}).get('inventory', {}).get('files', []):
            inventory[item['path']] = (rid, item)
    for row in rows:
        name = row['path']; p = exact_path(root, name)
        if p.is_absolute() and not p.is_relative_to(root):
            raise ValueError('retirement outside project')
        if name not in inventory:
            raise ValueError('retirement file absent from selected registered inventories')
        _, info = inventory[name]
        original = {k:v for k,v in info.items() if k != 'path'}
        if original != row['identity'] or identity(p) != original:
            raise ValueError('retirement file identity changed')
        if info['nlink'] != 1 or not stat.S_ISREG(info['mode']) or p.is_symlink():
            raise ValueError('retirement cannot waive shared/symlink protections')
        if p.suffix.lower() in {'.py','.sh','.json','.yaml','.yml','.toml','.md','.txt','.log'}:
            raise ValueError('retirement cannot delete conclusions or reproduction text')
        if protected(p, hard):
            raise ValueError('retirement conflicts with protected package/evidence/external consumer: '+name)
        # Existing preserve lists remain protected, even inside the retired group.
        for run in state['runs'].values():
            preserved = run.get('artifact_review', {}).get('review', {}).get('preserve', {})
            groups = preserved.values() if isinstance(preserved, dict) else [preserved]
            if any(name in group for group in groups):
                raise ValueError('retirement conflicts with preserved reproduction/evidence')

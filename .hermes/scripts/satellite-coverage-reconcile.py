#!/usr/bin/env python3
"""Reconcile satellite coverage in BOTH directions, idempotently.

Invariant: for every project P in the coding-hermes namespace,
  P enabled  <=>  P-{qa,pm,sync,dogfood} all exist and are enabled.
Satellites read P's board through a symlink, so an enabled satellite on a parked
target burns cap-1 slots on work whose owner is off, and a disabled satellite on a
live target silently removes that foreman's QA/dogfood/sync coverage.

Written 2026-09-19 after two sibling releases re-enabled targets mid-reconcile
(coding-hermes-tools, heading) — so this re-reads state on every run and reports
exactly what it changed. Run with --apply to act; default is a dry run.

  python3 ~/.hermes/scripts/satellite-coverage-reconcile.py [--apply] [--create]
"""
import argparse, json, sqlite3, sys, urllib.request, urllib.error

DB = '/home/kara/.hermes/coding-hermes/scheduler.db'
API = 'http://127.0.0.1:9090'
FAM = ('qa', 'pm', 'sync', 'dogfood')
FAM_NS = {'qa': 'qa', 'pm': 'pm', 'sync': 'duckbrain-sync', 'dogfood': 'dogfood'}
FAM_CD = {'qa': 43200, 'pm': 86400, 'sync': 43200, 'dogfood': 259200}
STAND = {'qa': '/home/kara/.hermes/stand-in/pm',
         'pm': '/home/kara/.hermes/stand-in/pm-lane',
         'sync': '/home/kara/.hermes/sync-workdirs',
         'dogfood': '/home/kara/.hermes/stand-in/dogfood'}


def key():
    for line in open('/home/kara/.hermes/.env'):
        if line.startswith('API_SERVER_KEY='):
            return line.split('=', 1)[1].strip()
    return ''


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + key(),
                                          'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--create', action='store_true', help='create missing satellite rows (default: report only)')
    a = ap.parse_args()
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    state = {n: (e, ns, wd) for n, e, ns, wd in con.execute(
        "SELECT name, enabled, COALESCE(namespace_id,''), COALESCE(workdir,'') FROM projects")}
    primaries = [(n, e) for n, (e, ns, wd) in state.items()
                 if ns == 'coding-hermes' and not n.endswith(tuple('-' + f for f in FAM))]
    changes, gaps, gaps_missing_live = [], [], []
    for p, pen in sorted(primaries):
        for f in FAM:
            sat = f'{p}-{f}'
            if sat not in state:
                gaps.append(sat)
                if pen and not a.create:
                    gaps_missing_live.append(sat)
                if a.create and pen:
                    body = {'name': sat, 'repo_url': state[p][2] and 'local:' + state[p][2] or 'local:',
                            'workdir': f'{STAND[f]}/{sat if f == "sync" else p}',
                            'cooldown_s': FAM_CD[f], 'cooldown_floor_s': FAM_CD[f],
                            'cooldown_ceiling_s': FAM_CD[f] * 8,
                            'namespace_id': FAM_NS[f], 'weight': 4, 'priority': 4,
                            'decay_rate': 1.0, 'prompt_mode': 'append'}
                    st = api('POST', '/api/v1/projects', body)
                    if st == 201 and pen and a.apply:
                        api('PUT', f'/api/v1/projects/{sat}', {'enabled': True})
                    changes.append(f'CREATE {sat} -> {st}')
                continue
            sen = state[sat][0]
            if pen and not sen:
                changes.append(f'ENABLE  {sat}  (target is live)')
                if a.apply:
                    api('PUT', f'/api/v1/projects/{sat}', {'enabled': True})
            elif not pen and sen:
                changes.append(f'DISABLE {sat}  (target is parked)')
                if a.apply:
                    api('PUT', f'/api/v1/projects/{sat}', {'enabled': False})
    print(f'{"APPLIED" if a.apply else "DRY RUN"} — {len(primaries)} primaries, {len(changes)} change(s), {len(gaps)} missing')
    for c in changes:
        print('  ' + c)
    parked = [g for g in gaps if g not in gaps_missing_live]
    if gaps_missing_live:
        print('  MISSING for a LIVE foreman (use --create): ' + ', '.join(gaps_missing_live))
    if parked:
        print(f'  {len(parked)} satellite(s) absent for parked/legacy projects — not a coverage gap')


if __name__ == '__main__':
    main()

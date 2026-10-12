"""TourMaps central lease, compatible with Contents API writers, using scoped SSH.

Every commit has the fetched central ref as parent; ordinary fast-forward push
is the atomic compare-and-swap. No forced ref, personal token or local fallback.
The deploy key is delegated to this service by Ahgarzon and only this repository.
"""
import argparse
import copy
import email.utils
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import uuid

BRANCH = 'codex/team-coordination'
FILE = 'coordination/state.json'
OWNER = 'Ahgarzon'
DOMAINS = {'brain', 'android-core', 'android-ui', 'ios', 'gateway',
           'release-android', 'release-ios', 'qa-isolated'}


def git(repo, *args, data=None):
    r = subprocess.run(['git', '-C', str(repo), *args], input=data, text=True,
                       capture_output=True, timeout=60, check=False)
    if r.returncode:
        raise RuntimeError('Scoped coordination Git request failed')
    return r.stdout.strip()


def server_time():
    with urllib.request.urlopen(urllib.request.Request(
            'https://api.github.com', headers={'User-Agent': 'TourMaps-builder'}), timeout=20) as r:
        return int(email.utils.parsedate_to_datetime(r.headers['Date']).timestamp())


def valid(state):
    if set(state) != {'schema', 'counter', 'domains'} or state['schema'] != 1:
        raise ValueError('Unexpected central schema')
    if type(state['counter']) is not int or state['counter'] < 0 or not set(state['domains']) <= DOMAINS:
        raise ValueError('Unexpected central domains')
    for x in state['domains'].values():
        if x is not None and (set(x) != {'owner', 'task', 'lease', 'fence', 'expires'}
                or x['owner'] not in {'Ahgarzon', 'jamesvidaltourmaps'}
                or not re.fullmatch(r'[a-z0-9-]{1,80}', x['task'])
                or not re.fullmatch(r'[0-9a-f]{32}', x['lease'])
                or type(x['expires']) is not int or type(x['fence']) is not int
                or not 0 < x['fence'] <= state['counter']):
            raise ValueError('Unexpected central lease')


def transition(state, now, action, lease=None):
    valid(state)
    state = copy.deepcopy(state)
    active = state['domains'].get('release-android')
    alive = active is not None and active['expires'] > now
    if action == 'acquire':
        if alive:
            return None, {'busy': True, 'owner': active['owner'], 'fence': active['fence']}
        state['counter'] += 1
        active = {'owner': OWNER, 'task': 'android-central-builder',
                  'lease': uuid.uuid4().hex, 'fence': state['counter'], 'expires': now + 1800}
        state['domains']['release-android'] = active
    else:
        if not alive or active['owner'] != OWNER or active['lease'] != lease:
            raise ValueError('Lease expired or not owned; no publication')
        if action == 'renew':
            active['expires'] = now + 1800
        elif action == 'release':
            state['domains']['release-android'] = None
        elif action != 'check':
            raise ValueError('Unknown transition')
    return state, {'busy': False, 'domain': 'release-android', **active, 'server_time': now}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['acquire', 'renew', 'check', 'release'])
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--lease-file', type=Path, required=True)
    a = p.parse_args()
    repo = a.repo.resolve()
    if not (repo / 'HEAD').exists():
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', '--bare', str(repo)], check=True, capture_output=True)
        git(repo, 'remote', 'add', 'origin', 'git@github.com:Ahgarzon/tourmaps-aios.git')
        git(repo, 'config', 'user.name', 'TourMaps scoped builder (Ahgarzon delegated)')
        git(repo, 'config', 'user.email', 'tourmaps-builder@users.noreply.github.com')
    if git(repo, 'remote', 'get-url', 'origin') != 'git@github.com:Ahgarzon/tourmaps-aios.git':
        raise ValueError('Wrong scoped coordinator')
    lease = json.loads(a.lease_file.read_text())['lease'] if a.action != 'acquire' else None
    for _ in range(4):
        git(repo, 'fetch', '--quiet', '--depth=1', 'origin', f'refs/heads/{BRANCH}')
        tip = git(repo, 'rev-parse', 'FETCH_HEAD')
        state = json.loads(git(repo, 'show', f'{tip}:{FILE}'))
        changed, receipt = transition(state, server_time(), a.action, lease)
        if changed is None or a.action == 'check':
            print(json.dumps(receipt))
            return 0
        blob = git(repo, 'hash-object', '-w', '--stdin', data=json.dumps(changed, sort_keys=True))
        git(repo, 'read-tree', tip)
        git(repo, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{FILE}')
        tree = git(repo, 'write-tree')
        commit = git(repo, 'commit-tree', tree, '-p', tip, data='coordination: scoped builder lease transition\n')
        try:
            git(repo, 'push', '--quiet', 'origin', f'{commit}:refs/heads/{BRANCH}')
        except RuntimeError:
            time.sleep(2)
            continue
        receipt['coordination_commit'] = commit
        a.lease_file.write_text(json.dumps(receipt))
        a.lease_file.chmod(0o600)
        print(json.dumps(receipt))
        return 0
    raise RuntimeError('Central race not resolved; no local fallback')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit('STOP: scoped central coordination unavailable; no publication')

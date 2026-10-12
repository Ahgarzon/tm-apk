"""Authorize a fixed central build request, never execute comment text."""
import json
import os
from pathlib import Path

REPOSITORY = 'Ahgarzon/tm-apk'
ISSUE = 10
TEAM_IDS = {114458437, 340242138}
COMMAND = '/tourmaps-build'


def authorized(event_name, event):
    if event_name in {'workflow_dispatch', 'schedule'}:
        return True
    if event_name != 'issue_comment' or event.get('action') != 'created':
        return False
    issue = event.get('issue', {})
    comment = event.get('comment', {})
    user_id = comment.get('user', {}).get('id')
    return (event.get('repository', {}).get('full_name') == REPOSITORY
            and issue.get('number') == ISSUE and not issue.get('pull_request')
            and comment.get('body') == COMMAND and type(user_id) is int
            and user_id in TEAM_IDS and event.get('sender', {}).get('id') == user_id)


def check_environment():
    event_name = os.environ.get('GITHUB_EVENT_NAME', '')
    event = (json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
             if event_name == 'issue_comment' else {})
    if not authorized(event_name, event):
        raise ValueError('Unapproved central build event; no source or signing access')

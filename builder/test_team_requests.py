import copy
import unittest
from pathlib import Path

from team_requests import authorized, TEAM_IDS


def event(user_id=340242138):
    return {'action': 'created', 'repository': {'full_name': 'Ahgarzon/tm-apk'},
            'issue': {'number': 10}, 'sender': {'id': user_id},
            'comment': {'body': '/tourmaps-build', 'user': {'id': user_id}}}


class TeamRequests(unittest.TestCase):
    def test_both_verified_ids_can_request_current_integrated_source(self):
        for user_id in TEAM_IDS:
            self.assertTrue(authorized('issue_comment', event(user_id)))

    def test_manual_and_schedule_still_authorized(self):
        for name in ['workflow_dispatch', 'schedule']:
            self.assertTrue(authorized(name, {}))
        self.assertFalse(authorized('pull_request_target', event()))

    def test_display_name_does_not_grant_access(self):
        value = event(123)
        value['comment']['user']['login'] = 'jamesvidaltourmaps'
        self.assertFalse(authorized('issue_comment', value))
        value = event('340242138')
        self.assertFalse(authorized('issue_comment', value))

    def test_no_arguments_code_edits_other_issue_or_pull_request(self):
        original = event()
        for key, value in [('action', 'edited'),
                           ('repository', {'full_name': 'outsider/tm-apk'}),
                           ('issue', {'number': 11}),
                           ('issue', {'number': 10, 'pull_request': {'url': 'not-used'}}),
                           ('sender', {'id': 123})]:
            changed = copy.deepcopy(original)
            changed[key] = value
            self.assertFalse(authorized('issue_comment', changed))
        for body in ['/tourmaps-build --branch=unreviewed', '/tourmaps-build\n',
                     '/tourmaps-build; echo private', 'instructions', '']:
            changed = copy.deepcopy(original)
            changed['comment']['body'] = body
            self.assertFalse(authorized('issue_comment', changed))

    def test_workflow_filters_before_assigning_runner_or_secrets(self):
        workflow = Path(__file__).parents[1] / '.github/workflows/android-pilot.yml'
        value = workflow.read_text()
        self.assertIn('issue_comment:\n    types: [created]', value)
        self.assertIn("github.event.comment.body == '/tourmaps-build'", value)
        self.assertIn('github.event.issue.number == 10', value)
        for user_id in TEAM_IDS:
            self.assertIn('github.event.comment.user.id == '+str(user_id), value)
        self.assertLess(value.index('    if:'), value.index('    runs-on:'))
        self.assertGreater(value.index('    concurrency:'), value.index('    if:'))
        self.assertNotIn('\nconcurrency:', value)
        self.assertNotIn('${{ github.event.comment.body }}', value)

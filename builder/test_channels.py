import unittest
from pathlib import Path
from channels import CHANNELS, identity, next_number, version_name


class Channels(unittest.TestCase):
    def test_native_permission_regression_is_required_before_compilation(self):
        code = (Path(__file__).parent / 'build.py').read_text()
        self.assertIn("run('microphone-policy-compile'", code)
        self.assertIn("run('microphone-policy-tests'", code)
        self.assertLess(code.index("run('microphone-policy-tests'"), code.index("run('apk-build'"))
        self.assertIn("'native_permission_policy': 'passed'", code)

    def test_signature_channels_are_not_interchangeable(self):
        self.assertNotEqual(CHANNELS['pilot']['cert'], CHANNELS['original']['cert'])
        self.assertEqual(CHANNELS['pilot']['compatible_with'], 54)
        self.assertEqual(CHANNELS['original']['compatible_with'], 55)

    def test_numbers_consider_both_channels_and_drafts(self):
        self.assertEqual(next_number([]), 57)
        self.assertEqual(next_number([{'tag_name': 'v1.0.35-tourmaps-original59', 'draft': True},
                                     {'tag_name': 'v1.0.34-tourmaps-pilot58'},
                                     {'tag_name': 'v1.0.32-original56'}]), 60)

    def test_version_tracks_source_baseline_and_candidate(self):
        self.assertEqual(version_name('name: app\nversion: 1.0.30+54\n', 57), '1.0.33')
        for value, number in [('version: 1.0.30', 57), ('version: 1.0.30+54', 54)]:
            with self.assertRaises(ValueError):
                version_name(value, number)

    def test_fixed_tag_identity_rejects_unknown_channel(self):
        self.assertEqual(identity('original', '1.0.33', 57),
                         ('v1.0.33-tourmaps-original57', 'TourMaps-Go-1.0.33+57-original.apk'))
        with self.assertRaises(ValueError):
            identity('../private', '1.0.33', 57)

    def test_both_native_gates_precede_drafts_and_original_is_existing(self):
        code = (Path(__file__).parent / 'build.py').read_text()
        self.assertIn("[('pilot', apk), ('original', original_apk)]", code)
        self.assertLess(code.index('qa = native_smoke(candidate'), code.index("run('release-draft-"))
        self.assertLess(code.index("hashlib.sha256(original_cert.stdout)"), code.index("run('sign-existing-original'"))
        self.assertNotIn('VERSION', code)
        self.assertIn("avd = 'TourMaps_Cloud_'+channel", code)

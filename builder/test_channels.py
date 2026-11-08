import unittest
import tempfile
from pathlib import Path
from channels import CHANNELS, identity, next_number, version_name
from source_gate import verify_dedicated_api_source


class Channels(unittest.TestCase):
    def test_native_permission_regression_is_required_before_compilation(self):
        code = (Path(__file__).parent / 'build.py').read_text()
        self.assertIn("run('microphone-policy-compile'", code)
        self.assertIn("run('microphone-policy-tests'", code)
        self.assertLess(code.index("run('microphone-policy-tests'"), code.index("run('apk-build'"))
        self.assertIn("'native_permission_policy': 'passed'", code)

    def test_release_uses_the_dedicated_api_instead_of_a_legacy_default(self):
        code = (Path(__file__).parent / 'build.py').read_text()
        command = code[code.index("run('apk-build'"):code.index("SOURCE_DIR, env)", code.index("run('apk-build'"))]
        self.assertIn('--dart-define=TOURMAPS_API_BASE_URL=https://tourmaps-api-62-171-153-218.sslip.io', command)

    def test_release_rejects_source_that_ignores_the_https_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            adapter = root / 'lib/services/tourmaps_api_config.dart'
            adapter.parent.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'select the dedicated'):
                adapter.write_text('const old = "http://94.72.117.162:3001";')
                verify_dedicated_api_source(root)
            adapter.write_text("const api = 'TOURMAPS_API_BASE_URL'; const fallback = 'https://tourmaps-api-62-171-153-218.sslip.io';")
            other = root / 'lib/old.dart'
            other.write_text("const old = 'http://94.72.117.162:3001';")
            with self.assertRaisesRegex(ValueError, 'retired cleartext'):
                verify_dedicated_api_source(root)
            other.write_text('const current = 1;')
            verify_dedicated_api_source(root)

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

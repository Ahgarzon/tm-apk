import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import native_qa


def result(code=0, stdout='', stderr=''):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


class NativeQA(unittest.TestCase):
    def test_crash_vocabulary_never_returns_private_fragments(self):
        labels = native_qa.crash_labels('FATAL EXCEPTION private-key /private/code '
            'UnsatisfiedLinkError dlopen failed libjnidispatch.so')
        self.assertEqual(labels, ['java-fatal', 'native-link-error',
                                  'native-library-load-failed', 'jna-library'])
        self.assertEqual(native_qa.crash_labels('secret-token'), [])

    def setUp(self):
        self.adb = ['adb', '-s', 'isolated-emulator']
        self.emulator = Mock()
        self.emulator.poll.return_value = None

    @patch('native_qa.time.sleep')
    @patch('native_qa.subprocess.run')
    def test_transient_offline_probe_then_complete_boot(self, run, sleep):
        run.side_effect = [result(1, stderr='device offline /private/secret'),
                           result(stdout=''), result(stdout='1\r\n')]
        native_qa.wait_until_booted(self.adb, {}, self.emulator)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch('native_qa.time.sleep')
    @patch('native_qa.subprocess.run')
    def test_nonzero_cannot_pass_even_with_boot_value(self, run, sleep):
        run.side_effect = [result(1, stdout='1'), result(stdout='1')]
        native_qa.wait_until_booted(self.adb, {}, self.emulator)
        self.assertEqual(run.call_count, 2)

    @patch('native_qa.subprocess.run')
    def test_emulator_exit_blocks_publication(self, run):
        self.emulator.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'emulator-exited'):
            native_qa.wait_until_booted(self.adb, {}, self.emulator)
        run.assert_not_called()

    @patch('native_qa.time.sleep')
    @patch('native_qa.time.monotonic', side_effect=[0, 0, 0, 1, 2])
    @patch('native_qa.subprocess.run', return_value=result(1, stderr='device offline private-token'))
    def test_offline_timeout_is_bounded_and_redacted(self, run, monotonic, sleep):
        with self.assertRaises(RuntimeError) as error:
            native_qa.wait_until_booted(self.adb, {}, self.emulator, timeout=2)
        self.assertIn('adb-device-offline', str(error.exception))
        self.assertNotIn('private-token', str(error.exception))
        self.assertEqual(run.call_count, 1)

    @patch('native_qa.time.sleep')
    @patch('native_qa.subprocess.run')
    def test_probe_timeout_can_recover(self, run, sleep):
        run.side_effect = [subprocess.TimeoutExpired(['private-token'], 10), result(stdout='1')]
        native_qa.wait_until_booted(self.adb, {}, self.emulator)
        self.assertEqual(run.call_count, 2)

    @patch('native_qa.subprocess.run', return_value=result(1, stderr='private-token'))
    def test_missing_app_is_phase_specific_not_success(self, run):
        with self.assertRaisesRegex(RuntimeError, 'application-process failed \\[android-app-process-missing\\]'):
            native_qa.native_output(self.adb, {}, 'application-process')

    @patch('native_qa.subprocess.run')
    def test_timeout_never_exposes_private_arguments(self, run):
        run.side_effect = subprocess.TimeoutExpired(['private-token'], 90)
        with self.assertRaises(RuntimeError) as error:
            native_qa.native_output(self.adb, {}, 'launch')
        self.assertEqual(str(error.exception), 'Native launch failed [adb-command-timeout]')

    @patch('native_qa.subprocess.run', return_value=result(stdout='Status: ok\n'))
    def test_success_and_unknown_phase(self, run):
        self.assertEqual(native_qa.native_output(self.adb, {}, 'launch'), 'Status: ok')
        with self.assertRaises(ValueError):
            native_qa.native_output(self.adb, {}, 'private-token')

import unittest
from diagnostics import failure_category


class Diagnostics(unittest.TestCase):
    def test_private_details_never_returned(self):
        for message, expected in [
            ('/private/source/path: No space left on device: hidden-value', 'runner-disk-full'),
            ('secret=value INSTALL_FAILED_UPDATE_INCOMPATIBLE private-file', 'android-update-certificate'),
            ('hidden-token java.lang.OutOfMemoryError: Java heap space', 'java-memory'),
            ('Credentials and unrecognized error text', 'subprocess-rejected'),
        ]:
            self.assertEqual(failure_category(message), expected)

    def test_downgrade_and_network_are_distinct(self):
        self.assertEqual(failure_category('INSTALL_FAILED_VERSION_DOWNGRADE'), 'android-version-downgrade')
        self.assertEqual(failure_category('Could not resolve private dependency'), 'dependency-network-or-resolution')

    def test_adb_failures_are_fixed_labels_without_private_text(self):
        for text, expected in [('device offline hidden-token', 'adb-device-offline'),
                               ('device not found /private/path', 'adb-device-unavailable'),
                               ('device unauthorized hidden-token', 'adb-device-unauthorized')]:
            self.assertEqual(failure_category(text), expected)

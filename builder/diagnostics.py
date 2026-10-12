"""Bounded public failure labels. Never return any fragment of private output."""


def failure_category(private_output):
    value = private_output.lower()
    patterns = [
        ('no space left on device', 'runner-disk-full'),
        ('not enough space', 'runner-disk-full'),
        ('licenses have not been accepted', 'android-sdk-license'),
        ('license for package', 'android-sdk-license'),
        ('install_failed_update_incompatible', 'android-update-certificate'),
        ('install_failed_version_downgrade', 'android-version-downgrade'),
        ('install_failed_insufficient_storage', 'android-avd-storage'),
        ('gradle build daemon disappeared', 'gradle-daemon-resource-or-crash'),
        ('java heap space', 'java-memory'),
        ('outofmemoryerror', 'java-memory'),
        ('could not resolve', 'dependency-network-or-resolution'),
        ('connection timed out', 'network-timeout'),
        ('connection reset', 'network-reset'),
        ('keystore was tampered with', 'existing-signing-store-rejected'),
        ('failed to load keystore', 'existing-signing-store-rejected'),
        ('compilation failed', 'source-compilation'),
    ]
    return next((label for needle, label in patterns if needle in value),
                'subprocess-rejected')

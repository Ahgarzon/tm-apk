"""Bounded ADB probes; public errors are fixed labels, never private output."""
import subprocess
import time
import re

from diagnostics import failure_category


def crash_labels(private_output):
    """Return only fixed vocabulary; never an exception/stack/log fragment."""
    value = private_output.lower()
    patterns = [
        ('fatal exception', 'java-fatal'), ('fatal signal 11', 'native-sigsegv'),
        ('fatal signal 6', 'native-sigabrt'), ('unsatisfiedlinkerror', 'native-link-error'),
        ('classnotfoundexception', 'class-not-found'),
        ('noclassdeffounderror', 'class-definition-missing'),
        ('securityexception', 'android-security-exception'),
        ('foregroundservicestartnotallowedexception', 'foreground-service-denied'),
        ('missingforegroundservicetypeexception', 'foreground-service-type-missing'),
        ('api key not found', 'maps-key-missing'),
        ('firebaseapp is not initialized', 'firebase-not-initialized'),
        ('dlopen failed', 'native-library-load-failed'),
        ('libjnidispatch', 'jna-library'), ('libvosk', 'vosk-library'),
        ('libflutter.so', 'flutter-engine'), ('impeller', 'impeller-renderer'),
        ('vulkan', 'vulkan-renderer'), ('outofmemoryerror', 'java-memory'),
        ('could not create root isolate', 'dart-root-isolate-failed'),
        ('unhandled exception', 'dart-unhandled-exception'),
        ('failed to load dynamic library', 'dart-library-load-failed'),
        ('check failed:', 'native-failed-assertion'),
        ('failed to create', 'initialization-failed'),
        ('is not compatible', 'runtime-incompatible'),
        ('permission denial', 'android-permission-denied'),
        ('killing ', 'android-process-kill-observed'),
        ('force stopping', 'android-force-stop-observed'),
        ('anr in ', 'android-anr-observed'),
        ('failed to initialize vulkan', 'vulkan-init-failed'),
        ('error running isolate', 'dart-isolate-error'),
        ('geolocatorforegroundservice', 'geolocator-foreground-service'),
        ('com.pravera.flutter_foreground_task', 'flutter-foreground-service'),
        ('starting fgs with type location', 'location-foreground-service-start'),
        ('foreground_service_location', 'location-foreground-permission'),
        ('while-in-use', 'while-in-use-permission'),
        ('com.google.android.gms.maps', 'maps-sdk'),
        ('com.google.firebase', 'firebase-sdk'),
        ('illegalstateexception', 'java-illegal-state'),
        ('illegalargumentexception', 'java-illegal-argument'),
        ('foregroundservicedidnotstartintimeexception', 'foreground-service-timeout'),
    ]
    return [label for needle, label in patterns if needle in value]


def target_crash_output(private_output):
    """Crash buffer only: retain blocks belonging to this fixed application."""
    blocks = re.split(r'(?=\S+\s+\S+\s+\d+\s+\d+\s+\S\s+AndroidRuntime: FATAL EXCEPTION)', private_output)
    return '\n'.join(x for x in blocks if re.search(
        r'(?:Process:|Cmdline:)\s+com\.gopluss\.tourmapsgo(?:,|\s|$)', x))


def assert_no_target_crash(adb, env):
    value = native_output([*adb, 'logcat', '-d', '-b', 'crash'], env, 'crash-check')
    target = target_crash_output(value)
    if target:
        print('Target application fatal fixed labels: '+','.join(crash_labels(target) or ['unclassified']), flush=True)
        raise RuntimeError('Target application crashed; no publication')


def diagnose_crash(adb, env, channel='pilot'):
    try:
        result = subprocess.run([str(x) for x in [*adb, 'logcat', '-d', '-b', 'all']],
                                env=env, capture_output=True, text=True, timeout=30)
        labels = crash_labels(result.stdout) if result.returncode == 0 else ['diagnostic-unavailable']
    except subprocess.TimeoutExpired:
        labels = ['diagnostic-timeout']
    print('Native diagnostic fixed labels: '+','.join(labels or ['unclassified']), flush=True)
    crashes = subprocess.run([str(x) for x in [*adb, 'logcat', '-d', '-b', 'crash']],
                             env=env, capture_output=True, text=True, timeout=30)
    target = target_crash_output(crashes.stdout) if crashes.returncode == 0 else ''
    print('Target application fatal fixed labels: '+','.join(
        crash_labels(target) if target else ['none-observed']), flush=True)
    # Detailed target-only diagnostics go via a restricted forced-command key
    # to private VPS storage, never Actions logs/artifacts or public Git.
    if target:
        try:
            import build
            import json
            import os
            build.key('TOURMAPS_DIAGNOSTIC_SSH_KEY')
            payload = json.dumps({'run_id': os.environ['GITHUB_RUN_ID'],
                                  'channel': channel, 'target_crash': target[:180000]})
            received = subprocess.run(['ssh', '-T', '-i', str(build.ROOT / 'TOURMAPS_DIAGNOSTIC_SSH_KEY'),
                '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
                '-o', 'ConnectTimeout=15', '-o', 'UserKnownHostsFile='+str(build.TOOLS / 'vps_known_hosts'),
                'aios@62.171.166.79', 'receive-only'], input=payload, capture_output=True,
                text=True, timeout=45)
            print('Private target diagnostic received='+str(received.returncode == 0), flush=True)
        except Exception:
            print('Private diagnostic transport unavailable; no public fallback.', flush=True)
    try:
        result = subprocess.run([str(x) for x in [*adb, 'shell', 'dumpsys', 'activity',
            'exit-info', 'com.gopluss.tourmapsgo']], env=env, capture_output=True, text=True, timeout=30)
        reasons = sorted(set(re.findall(r'reason=(\d+)\s*\(', result.stdout)))
        print('Native diagnostic Android numeric exit reasons: '+','.join(
            x for x in reasons if x.isdecimal() and len(x) <= 2), flush=True)
    except subprocess.TimeoutExpired:
        print('Native exit diagnostic timed out.', flush=True)


PHASES = {'previous-install-state', 'updated-install-state', 'launch',
          'application-process', 'crash-check'}


def native_output(args, env, phase):
    if phase not in PHASES:
        raise ValueError('Unknown native verification phase')
    try:
        result = subprocess.run([str(x) for x in args], env=env,
                                capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Native '+phase+' failed [adb-command-timeout]') from None
    if result.returncode:
        category = failure_category(result.stdout+'\n'+result.stderr)
        if phase == 'application-process' and category == 'subprocess-rejected':
            category = 'android-app-process-missing'
        raise RuntimeError('Native '+phase+' failed ['+category+']')
    return result.stdout.strip()


def wait_until_booted(adb, env, emulator, timeout=240):
    """ADB transport can be online before Android boots; tolerate bounded probes.

    Only exit0 AND sys.boot_completed=1 pass. No install/update/launch is retried
    or treated as successful here. Failure to boot still prevents publication.
    """
    until = time.monotonic()+timeout
    category = 'android-not-booted'
    while time.monotonic() < until:
        if emulator.poll() is not None:
            raise RuntimeError('Native boot failed [emulator-exited]')
        remaining = until-time.monotonic()
        if remaining <= 0:
            break
        try:
            result = subprocess.run([str(x) for x in [*adb, 'shell', 'getprop', 'sys.boot_completed']],
                                    env=env, capture_output=True, text=True,
                                    timeout=min(10, remaining))
            if result.returncode == 0 and result.stdout.strip() == '1':
                return
            category = (failure_category(result.stdout+'\n'+result.stderr)
                        if result.returncode else 'android-not-booted')
        except subprocess.TimeoutExpired:
            category = 'adb-command-timeout'
        time.sleep(min(2, max(0, until-time.monotonic())))
    raise RuntimeError('Native boot failed ['+category+']; no untested publication')

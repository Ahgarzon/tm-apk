"""Bounded ADB probes; public errors are fixed labels, never private output."""
import subprocess
import time

from diagnostics import failure_category


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

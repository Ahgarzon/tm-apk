"""No build/release/send: probe known public APKs on disposable isolated AVDs."""
import contextlib
import os
from pathlib import Path
import re
import subprocess
import time

import build
from native_qa import diagnose_crash, native_output, wait_until_booted

CASES = [
    ('pilot54', 'https://github.com/Ahgarzon/tm-apk/releases/download/v1.0.30-tourmaps-pilot54/TourMaps-Go-1.0.30%2B54-candidata.apk',
     'c1c8b4c00d3e9c2f6b60551f4e498435ff509a1b7f5a8dcb1837d90dfd69ea2d', build.CERT),
    ('original55', 'https://github.com/jamesvidaltourmaps/tourmaps-apk/releases/download/v1.0.31-original55/TourMaps-Go-1.0.31-55.apk',
     '9ee4ac851370e4d13677ccfdb0372ef6c2d17e635704cf974bde2c008826af5a',
     '263c2fab542e49c0219a35854cd2816a06fca0f99569b031dadf4cc6f735aba4'),
]


def probe(label, url, sha, cert, env, sdk, image):
    apk = build.ROOT / (label+'.apk')
    build.download(url, apk, sha)
    signed = build.output([sdk / 'build-tools/36.0.0/apksigner', 'verify', '--print-certs', apk], env=env)
    if cert not in signed.lower():
        raise ValueError('Known baseline certificate mismatch')
    badge = build.output([sdk / 'build-tools/36.0.0/aapt', 'dump', 'badging', apk], env=env)
    activity = re.search(r"launchable-activity: name='([^']+)'", badge)
    if not activity or "name='"+build.PACKAGE+"'" not in badge.splitlines()[0]:
        raise ValueError('Known baseline identity mismatch')
    build.run('create-'+label, [sdk / 'cmdline-tools/latest/bin/avdmanager', 'create', 'avd',
        '--name', label, '--package', image, '--device', 'pixel_6'], env=env, data='no\n')
    log = (build.LOG / (label+'-emulator.log')).open('ab')
    process = subprocess.Popen([str(sdk / 'emulator/emulator'), '-avd', label,
        '-port', '5584', '-no-window', '-no-audio', '-no-boot-anim', '-no-snapshot',
        '-gpu', 'swiftshader_indirect', '-memory', '2048', '-cores', '2', '-accel', 'on'],
        env=env, stdout=log, stderr=subprocess.STDOUT)
    adb = [sdk / 'platform-tools/adb', '-s', 'emulator-5584']
    try:
        build.run('wait-'+label, [*adb, 'wait-for-device'], env=env, timeout=180)
        wait_until_booted(adb, env, process)
        build.run('install-'+label, [*adb, 'install', apk], env=env, timeout=120)
        build.run('clear-'+label, [*adb, 'logcat', '-c'], env=env)
        launch = native_output([*adb, 'shell', 'am', 'start', '-W', '-n',
                                build.PACKAGE+'/'+activity[1]], env, 'launch')
        if 'Status: ok' not in launch or 'Error:' in launch:
            raise RuntimeError('Known baseline launch rejected')
        time.sleep(20)
        result = subprocess.run([str(x) for x in [*adb, 'shell', 'pidof', build.PACKAGE]],
                                env=env, capture_output=True, text=True, timeout=30)
        print('Known public baseline '+label+': process_alive='+str(
            result.returncode == 0 and bool(re.fullmatch(r'\d+', result.stdout.strip()))), flush=True)
        diagnose_crash(adb, env)
    finally:
        with contextlib.suppress(Exception):
            subprocess.run([str(x) for x in [*adb, 'emu', 'kill']], env=env,
                           capture_output=True, timeout=10)
        with contextlib.suppress(Exception):
            process.wait(timeout=15)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log.close()


def main():
    build.COORD_ENV = build.key('TOURMAPS_COORDINATION_SSH_KEY')
    # Both domains: a diagnostic must never race a real Android build/native QA.
    release = build.lease('acquire')
    if release.get('busy'):
        print('Diagnostic waiting for authorized Android reservation; no duplicate job.')
        return
    qa = False
    try:
        receipt = build.lease('acquire', 'qa-isolated')
        if receipt.get('busy'):
            print('Diagnostic waiting for isolated QA reservation.')
            return
        qa = True
        sdk = Path(os.environ['ANDROID_HOME'])
        env = {k: v for k, v in os.environ.items() if not k.startswith('TOURMAPS_')
               and k not in {'GH_TOKEN', 'GITHUB_TOKEN', 'GITHUB_PAT', 'GIT_SSH_COMMAND'}}
        env.update({'JAVA_HOME': os.environ['JAVA_HOME_17_X64'],
                    'ANDROID_USER_HOME': str(build.ROOT / '.android'),
                    'ANDROID_AVD_HOME': str(build.ROOT / 'avd')})
        Path(env['ANDROID_AVD_HOME']).mkdir(mode=0o700, exist_ok=True)
        image = 'system-images;android-35;google_apis;x86_64'
        build.run('probe-sdk', [sdk / 'cmdline-tools/latest/bin/sdkmanager',
                  'emulator', 'build-tools;36.0.0', image], env=env)
        if not Path('/dev/kvm').exists():
            raise RuntimeError('Diagnostic needs ephemeral KVM')
        build.run('probe-kvm', ['sudo', '-n', 'chmod', 'a+rw', '/dev/kvm'])
        for case in CASES:
            build.lease('check')
            build.lease('check', 'qa-isolated')
            probe(*case, env, sdk, image)
        print('Diagnostic only; no APK built, published, delivered or approved.')
    finally:
        if qa:
            with contextlib.suppress(Exception):
                build.lease('release', 'qa-isolated')
        with contextlib.suppress(Exception):
            build.lease('release')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Diagnostic failed safely; no private log exposure or publication.')
        raise SystemExit(1)

"""Reviewed TourMaps Android pilot builder. Public orchestration, private source/config.

No production/store deployment or messages. Public logs contain milestones only;
private source/test/build output never leaves the ephemeral runner. The VPS
delivery worker verifies the published artifact independently before WhatsApp.
"""
import base64
import contextlib
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.parse
import urllib.request
import zipfile

CHANNEL = 'Ahgarzon/tm-apk'
SOURCE = 'git@github.com:Ahgarzon/tourmaps-mobile-ios.git'
BRANCH = 'codex/testflight-beta'
CERT = '79f0e7b026ef0634ad7b8b7f37fc07f40aac874897efa1ea0e0593bc05a8b8d5'
PACKAGE = 'com.gopluss.tourmapsgo'
VERSION = '1.0.31'
FLUTTER = '3.47.5'
ROOT = Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'tourmaps-builder'
ROOT.mkdir(mode=0o700, exist_ok=True)
SOURCE_DIR = ROOT / 'source'
LOG = ROOT / 'private-logs'
LOG.mkdir(mode=0o700, exist_ok=True)
TOOLS = Path(__file__).resolve().parent
LOCK = threading.Lock()
STOP = threading.Event()
FAILED_RENEWAL = threading.Event()


def request(url, data=None, token=None):
    headers = {'User-Agent': 'TourMaps-central-builder', 'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=45) as r:
        return json.load(r)


def run(label, args, cwd=None, env=None, timeout=1800):
    with (LOG / (label + '.log')).open('ab') as log:
        r = subprocess.run([str(x) for x in args], cwd=cwd, env=env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if r.returncode:
        raise RuntimeError(label + ' failed; no APK promotion or private log exposure')


def output(args, cwd=None, env=None):
    r = subprocess.run([str(x) for x in args], cwd=cwd, env=env, capture_output=True,
                       text=True, timeout=90)
    if r.returncode:
        raise RuntimeError('Verification command failed; no private output exposure')
    return r.stdout.strip()


def download(url, destination, expected=None):
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=180) as response, destination.open('wb') as stream:
        while block := response.read(1024 * 1024):
            stream.write(block)
            h.update(block)
    if expected and h.hexdigest().lower() != expected.lower():
        raise RuntimeError('Tool/resource download hash mismatch')
    return h.hexdigest()


def key(name):
    file = ROOT / name
    value = os.environ[name]
    if not value.startswith('-----BEGIN OPENSSH PRIVATE KEY-----'):
        raise ValueError('Required scoped source/coordination capability absent')
    file.write_text(value.rstrip()+'\n')
    file.chmod(0o600)
    return {'GIT_SSH_COMMAND': f'ssh -i {file} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile={TOOLS / "github_known_hosts"}'}


def lease(action):
    with LOCK:
        env = {**os.environ, **COORD_ENV}
        text = output([sys.executable, TOOLS / 'coordination.py', action,
                       '--repo', ROOT / 'coordination.git', '--lease-file', ROOT / 'lease.json'], env=env)
        return json.loads(text)


def renew():
    while not STOP.wait(300):
        try:
            lease('renew')
        except Exception:
            FAILED_RENEWAL.set()
            return


def latest_source():
    value = output(['git', 'ls-remote', SOURCE, 'refs/heads/' + BRANCH], env=SOURCE_ENV)
    sha = value.split()[0]
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Integrated source unavailable')
    return sha


def resources():
    wrapper = SOURCE_DIR / 'android/gradle/wrapper/gradle-wrapper.jar'
    download('https://raw.githubusercontent.com/gradle/gradle/v8.14.0/gradle/wrapper/gradle-wrapper.jar',
             wrapper, '7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172')
    archive = ROOT / 'vosk.zip'
    download('https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip', archive,
             '09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f')
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path = Path(item.filename)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'vosk-model-small-es-0.42' or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe model archive')
        z.extractall(ROOT / 'model')
    shutil.move(ROOT / 'model/vosk-model-small-es-0.42',
                SOURCE_DIR / 'android/app/src/main/assets/nadia-model')
    (SOURCE_DIR / 'android/gradlew').chmod(0o755)


def prepare_tools():
    metadata = request('https://storage.googleapis.com/flutter_infra_release/flutter/releases/releases_linux.json')
    matches = [x for x in metadata['releases'] if x['version'] == FLUTTER and x['channel'] == 'stable']
    if len(matches) != 1 or not re.fullmatch(r'[a-f0-9]{64}', matches[0]['sha256']):
        raise ValueError('Pinned official Flutter not available')
    archive = ROOT / 'flutter.tar.xz'
    download(metadata['base_url'] + '/' + matches[0]['archive'], archive, matches[0]['sha256'])
    with tarfile.open(archive) as tar:
        tar.extractall(ROOT, filter='data')
    sdk = Path(os.environ['ANDROID_HOME'])
    manager = sdk / 'cmdline-tools/latest/bin/sdkmanager'
    env = {k: v for k, v in os.environ.items() if not k.startswith('TOURMAPS_') and k not in {'GH_TOKEN', 'GITHUB_TOKEN', 'GITHUB_PAT', 'GIT_SSH_COMMAND'}}
    env.update({'JAVA_HOME': os.environ['JAVA_HOME_17_X64'],
                'ANDROID_USER_HOME': str(ROOT / '.android'), 'PUB_CACHE': str(ROOT / 'pub-cache'),
                'GRADLE_USER_HOME': str(ROOT / 'gradle'), 'FLUTTER_SUPPRESS_ANALYTICS': 'true',
                'CI': 'true'})
    env['PATH'] = str(ROOT / 'flutter/bin') + ':' + env['JAVA_HOME'] + '/bin:' + env['PATH']
    run('sdk', [manager, 'platforms;android-36', 'build-tools;36.0.0', 'ndk;28.2.13676358'], env=env)
    env['ORG_GRADLE_PROJECT_TOURMAPS_MAPS_API_KEY'] = os.environ['TOURMAPS_MAPS_ANDROID_KEY']
    env['ORG_GRADLE_PROJECT_TOURMAPS_PILOT_SIGNING'] = 'true'
    return env


def main():
    global SOURCE_ENV, COORD_ENV
    SOURCE_ENV = {**os.environ, **key('TOURMAPS_SOURCE_SSH_KEY')}
    COORD_ENV = key('TOURMAPS_COORDINATION_SSH_KEY')
    source = latest_source()
    expected = os.environ.get('REQUESTED_SOURCE', '')
    if expected and expected != source:
        raise ValueError('Requested source is no longer current; no stale build')
    releases = request(f'https://api.github.com/repos/{CHANNEL}/releases?per_page=30', token=os.environ['GH_TOKEN'])
    maximum = 55
    for release in releases:
        match = re.fullmatch(r'v[0-9.]+-tourmaps-pilot(\d+)', release['tag_name'])
        if match:
            maximum = max(maximum, int(match[1]))
        if release['draft']:
            continue
        for asset in release['assets']:
            if asset['name'] in {'tourmaps-release.json', 'map54-manifest.json'}:
                manifest = request(asset['browser_download_url'])
                if manifest.get('source_commit') == source and manifest.get('signing', {}).get('certificate_sha256') == CERT:
                    print('Current integrated source already has a verified pilot candidate; no rebuild.')
                    return
    receipt = lease('acquire')
    if receipt.get('busy'):
        print('Another authorized Android release owns the central lease; queued for a later cycle.')
        return
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        number = maximum + 1
        run('clone', ['git', 'clone', '--quiet', '--depth=1', '--single-branch', '--branch', BRANCH, SOURCE, SOURCE_DIR], env=SOURCE_ENV)
        if output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE_DIR) != source:
            raise ValueError('Source changed during checkout; retry a fresh cycle')
        resources()
        run('linux-filemode', ['git', 'config', 'core.fileMode', 'false'], SOURCE_DIR)
        env = prepare_tools()
        android = ROOT / '.android'
        android.mkdir(mode=0o700, exist_ok=True)
        (android / 'debug.keystore').write_bytes(base64.b64decode(os.environ['TOURMAPS_PILOT_KEYSTORE_B64'], validate=True))
        (android / 'debug.keystore').chmod(0o600)
        cert = output([Path(env['JAVA_HOME']) / 'bin/keytool', '-J-Duser.language=en', '-list', '-v',
                       '-keystore', android / 'debug.keystore', '-storepass', 'android', '-alias', 'androiddebugkey'], env=env)
        digest = re.search(r'SHA256:\s*([A-Fa-f0-9:]+)', cert)
        if not digest or digest[1].replace(':', '').lower() != CERT:
            raise ValueError('Existing pilot certificate differs; no replacement key generated')
        firebase = json.loads(os.environ['TOURMAPS_FIREBASE_ANDROID_JSON'])
        if PACKAGE not in [x.get('client_info', {}).get('android_client_info', {}).get('package_name') for x in firebase.get('client', [])]:
            raise ValueError('Wrong Android Firebase client')
        (SOURCE_DIR / 'android/app/google-services.json').write_text(json.dumps(firebase))
        flutter = ROOT / 'flutter/bin/flutter'
        run('dependencies', [flutter, 'pub', 'get', '--enforce-lockfile'], SOURCE_DIR, env)
        run('flutter-tests', [flutter, 'test', '--no-pub'], SOURCE_DIR, env)
        run('node-tests', ['node', '--test', *sorted(glob.glob(str(SOURCE_DIR / 'tourmaps-ci/ios/*.test.mjs')))], SOURCE_DIR, env)
        run('analysis', [flutter, 'analyze', '--no-pub', '--no-fatal-infos', '--no-fatal-warnings'], SOURCE_DIR, env)
        print('Source tests and error-level analysis passed; compiling compatible Android pilot.')
        lease('check')
        run('apk-build', [flutter, 'build', 'apk', '--release', '--no-pub', '--build-name='+VERSION,
            '--build-number='+str(number), '--dart-define=ENABLE_TOURMAPS_JARVIS=true',
            '--dart-define=TOURMAPS_JARVIS_URL=https://jarvis.angelszs.site/api/v1/tourist/chat'], SOURCE_DIR, env)
        apk = SOURCE_DIR / 'build/app/outputs/flutter-apk/app-release.apk'
        build_tools = Path(env['ANDROID_HOME']) / 'build-tools/36.0.0'
        signed = output([build_tools / 'apksigner', 'verify', '--print-certs', apk], env=env)
        if CERT not in signed.lower():
            raise ValueError('APK certificate mismatch')
        badging = output([build_tools / 'aapt', 'dump', 'badging', apk], env=env).splitlines()[0]
        if not all(x in badging for x in [f"name='{PACKAGE}'", f"versionCode='{number}'", f"versionName='{VERSION}'"]):
            raise ValueError('APK identity mismatch')
        # Linux execute-bit normalization is local Git configuration, not a source edit.
        if output(['git', 'status', '--porcelain'], cwd=SOURCE_DIR):
            raise ValueError('Source mutated during build')
        filename = f'TourMaps-Go-{VERSION}+{number}-candidata.apk'
        tag = f'v{VERSION}-tourmaps-pilot{number}'
        asset = ROOT / filename
        shutil.copyfile(apk, asset)
        sha = hashlib.file_digest(asset.open('rb'), 'sha256').hexdigest()
        manifest = {'application': 'TourMaps GO+', 'platform': 'android', 'version': VERSION,
                    'build_number': number, 'package': PACKAGE, 'source_commit': source,
                    'clean_tree_at_build': True, 'channel': 'pilot-not-Play-Store',
                    'builder_run': os.environ['GITHUB_RUN_URL'],
                    'signing': {'signature_verified': True, 'certificate_sha256': CERT, 'compatible_with': 54},
                    'qa': {'flutter_tests': 'passed', 'node_tests': 'passed', 'analysis_errors': 0,
                           'physical_device': False, 'native_runtime_smoke': False},
                    'artifact': {'filename': filename, 'bytes': asset.stat().st_size, 'sha256': sha,
                                 'url': f'https://github.com/{CHANNEL}/releases/download/{tag}/'+urllib.parse.quote(filename, safe='')}}
        manifest_file = ROOT / 'tourmaps-release.json'
        manifest_file.write_text(json.dumps(manifest, indent=2))
        if FAILED_RENEWAL.is_set() or latest_source() != source:
            raise ValueError('Lease/source changed; late artifact must not replace current work')
        lease('check')
        # Draft first. Failed or incomplete upload never becomes a public release.
        run('release-draft', ['gh', 'release', 'create', tag, '--repo', CHANNEL, '--draft', '--prerelease',
             '--target', os.environ['GITHUB_SHA'], '--title', f'TourMaps {VERSION}+{number} — piloto Android',
             '--notes', f'Fuente revisada: {source}. Firma compatible con piloto +54. Pruebas de código aprobadas; validación física pendiente. No es Google Play.'], timeout=90)
        run('release-upload', ['gh', 'release', 'upload', tag, asset, manifest_file, '--repo', CHANNEL], timeout=240)
        if FAILED_RENEWAL.is_set() or latest_source() != source:
            raise ValueError('Source moved before promotion; preserve draft only')
        lease('check')
        run('release-publish', ['gh', 'release', 'edit', tag, '--repo', CHANNEL, '--draft=false'], timeout=90)
        downloaded = ROOT / 'anonymous-check.apk'
        if download(manifest['artifact']['url'], downloaded) != sha or downloaded.stat().st_size != asset.stat().st_size:
            raise ValueError('Public full download verification failed; no delivery approval')
        print(json.dumps({'published': True, 'version': f'{VERSION}+{number}', 'source': source,
                          'sha256': sha, 'download': manifest['artifact']['url'], 'physical_qa': False}))
    finally:
        STOP.set()
        thread.join(timeout=30)
        with contextlib.suppress(Exception):
            lease('release')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Exception text is ours; private subprocess output is never included.
        print('STOP: '+str(error), file=sys.stderr)
        raise SystemExit(1)

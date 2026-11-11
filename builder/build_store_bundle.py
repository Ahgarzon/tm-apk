"""Build one same-source, original-signed AAB as a private GitHub draft only.

No Play API credentials, store upload, APK publication or WhatsApp delivery.
Standard public ubuntu-24.04 compute; no Actions artifacts or cache storage.
"""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import zipfile

import build as b
from channels import CHANNELS, next_number, version_name
from release_notes import notification_summary
from store_artifacts import identity, native_16k, property_value, verify_signed_jar
from team_requests import TEAM_IDS

BUNDLETOOL_VERSION = '1.18.3'
BUNDLETOOL_SHA256 = 'a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29'
MANIFEST = 'tourmaps-store-release.json'


def notes(source):
    repo = b.ROOT/'coordination.git'
    env = {**os.environ, **b.COORD_ENV}
    b.output(['git','fetch','--quiet','--depth=1','origin',
              'refs/heads/main:refs/remotes/origin/store-notes'],cwd=repo,env=env)
    commit = b.output(['git','rev-parse','refs/remotes/origin/store-notes'],cwd=repo)
    return notification_summary(b.output(['git','show',commit+':releases/change-notes.json'],cwd=repo),source),commit


def existing(source, releases):
    for release in releases:
        if not re.fullmatch(r'v[0-9.]+-tourmaps-store\d+',release['tag_name']): continue
        for asset in release['assets']:
            if asset['name'] != MANIFEST: continue
            data=b.request(asset['url'],token=os.environ['GH_TOKEN'],accept='application/octet-stream')
            if (data.get('source_commit')==source and data.get('format')=='aab'
                    and data.get('signing',{}).get('certificate_sha256')==CHANNELS['original']['cert']
                    and data.get('qa',{}).get('native_runtime_smoke') is True
                    and any(x['name']==data.get('artifact',{}).get('filename')
                            and x['size']==data['artifact']['bytes'] for x in release['assets'])):
                return release['tag_name']
    return None


def main():
    actor=os.environ.get('GITHUB_ACTOR_ID','')
    if (os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch'
            or os.environ.get('GITHUB_REPOSITORY')!=b.CHANNEL or not actor.isdigit()
            or int(actor) not in TEAM_IDS):
        raise ValueError('Only an authorized team member may request the fixed store draft')
    repository=b.request('https://api.github.com/repos/'+b.CHANNEL,token=os.environ['GH_TOKEN'])
    if repository.get('private') is not False or repository.get('visibility')!='public':
        raise ValueError('Free standard public runner required; no private billed fallback')
    expected=os.environ.get('REQUESTED_SOURCE','')
    if not re.fullmatch(r'[a-f0-9]{40}',expected): raise ValueError('Exact source required')
    b.SOURCE_ENV={**os.environ,**b.key('TOURMAPS_SOURCE_SSH_KEY')}
    b.COORD_ENV=b.key('TOURMAPS_COORDINATION_SSH_KEY')
    source=b.latest_source()
    if source!=expected: raise ValueError('Requested source advanced; no stale bundle')
    releases=b.request(f'https://api.github.com/repos/{b.CHANNEL}/releases?per_page=100',token=os.environ['GH_TOKEN'])
    old=existing(source,releases)
    if old:
        print('This source already has a verified store draft; no rebuild or delivery. '+old)
        return
    other=b.request('https://api.github.com/repos/jamesvidaltourmaps/tourmaps-apk/releases?per_page=100')
    if b.lease('acquire').get('busy'):
        print('Existing Android publisher preserved; no duplicate build.');return
    thread=threading.Thread(target=b.renew,daemon=True);thread.start()
    private_files=[]
    def private_write(path, data):
        handle=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        private_files.append(path)
        with os.fdopen(handle,'wb') as stream: stream.write(data)
    try:
        if b.lease('acquire','qa-isolated').get('busy'):
            print('Existing native QA reservation preserved.');return
        b.QA_OWNED=True
        changes,notes_commit=notes(source)
        number=next_number(releases+other)
        env=b.prepare_source(source,pilot_signing=False)
        version=version_name((b.SOURCE_DIR/'pubspec.yaml').read_text(),number)
        tag,filename=identity(version,number)
        ignored=b.output(['git','check-ignore','--','android/key.properties','android/app/mi_tourmaps_key.jks'],cwd=b.SOURCE_DIR).splitlines()
        if set(ignored)!={'android/key.properties','android/app/mi_tourmaps_key.jks'}:
            raise ValueError('Private signing files must remain outside source control')
        signing=json.loads(os.environ['TOURMAPS_ORIGINAL_SIGNING_JSON'])
        key=b.SOURCE_DIR/'android/app/mi_tourmaps_key.jks'
        props=b.SOURCE_DIR/'android/key.properties'
        if key.exists() or props.exists(): raise ValueError('Unexpected signing input preserved')
        private_write(key,base64.b64decode(signing['keystore_b64'],validate=True))
        private_write(props,('\n'.join(k+'='+property_value(signing[k]) for k in ['storePassword','keyAlias','keyPassword'])+'\n').encode('ascii'))
        # bundletool supports file: passwords, not apksigner's env: syntax.
        # Keep passwords off argv and reject truncation by its first-line reader.
        if any(not isinstance(signing[k],str) or not signing[k] or '\n' in signing[k] or '\r' in signing[k]
               for k in ['storePassword','keyPassword']):
            raise ValueError('Existing signing passwords must fit the bundletool file format')
        storepass=b.ROOT/'store-password.private';keypass=b.ROOT/'key-password.private'
        private_write(storepass,signing['storePassword'].encode('utf-8'))
        private_write(keypass,signing['keyPassword'].encode('utf-8'))
        env={**env,'TM_ORIGINAL_STOREPASS':signing['storePassword'],'TM_ORIGINAL_KEYPASS':signing['keyPassword']}
        java_bin=Path(env['JAVA_HOME'])/'bin'
        cert=subprocess.run([str(java_bin/'keytool'),'-exportcert','-keystore',str(key),
            '-storepass:env','TM_ORIGINAL_STOREPASS','-alias',signing['keyAlias']],env=env,capture_output=True,timeout=30)
        if cert.returncode or hashlib.sha256(cert.stdout).hexdigest()!=CHANNELS['original']['cert']:
            raise ValueError('Existing original certificate mismatch; no replacement key')
        realtime=b.android_realtime_defines(json.loads((b.SOURCE_DIR/'android/app/google-services.json').read_text()))
        b.lease('check')
        print('Source checks passed; building an original-signed store bundle only.',flush=True)
        b.run('store-bundle-build',[b.ROOT/'flutter/bin/flutter','build','appbundle','--release','--no-pub',
            '--build-name='+version,'--build-number='+str(number),'--dart-define=ENABLE_TOURMAPS_JARVIS=true',
            '--dart-define=TOURMAPS_API_BASE_URL=https://tourmaps-api-62-171-153-218.sslip.io',
            '--dart-define=TOURMAPS_JARVIS_URL=https://jarvis.angelszs.site/api/v1/tourist/chat',*realtime],b.SOURCE_DIR,env)
        bundle=b.SOURCE_DIR/'build/app/outputs/bundle/release/app-release.aab'
        verify_signed_jar(bundle,key,signing['keyAlias'],env,java_bin,CHANNELS['original']['cert'])
        tool=b.ROOT/'bundletool.jar'
        b.download(f'https://github.com/google/bundletool/releases/download/{BUNDLETOOL_VERSION}/bundletool-all-{BUNDLETOOL_VERSION}.jar',tool,BUNDLETOOL_SHA256)
        prefix=[java_bin/'java','-jar',tool]
        b.run('bundle-validate',[*prefix,'validate','--bundle='+str(bundle)],env=env)
        apks=b.ROOT/'store-universal.apks'
        b.run('bundle-universal',[*prefix,'build-apks','--bundle='+str(bundle),'--output='+str(apks),
            '--mode=universal','--ks='+str(key),'--ks-key-alias='+signing['keyAlias'],
            '--ks-pass=file:'+str(storepass),'--key-pass=file:'+str(keypass)],env=env)
        apk=b.ROOT/'store-universal.apk'
        with zipfile.ZipFile(apks) as z:
            item=z.getinfo('universal.apk')
            if not 10_000_000<item.file_size<512_000_000: raise ValueError('Unexpected universal APK size')
            with z.open(item) as source_stream,apk.open('wb') as target_stream: shutil.copyfileobj(source_stream,target_stream)
        tools=Path(env['ANDROID_HOME'])/'build-tools/36.0.0'
        certs=b.output([tools/'apksigner','verify','--print-certs',apk],env=env)
        digests=re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([a-f0-9]{64})$',certs,re.M)
        if digests!=[CHANNELS['original']['cert']]: raise ValueError('Universal APK signer mismatch')
        b.run('store-zipalign',[tools/'zipalign','-c','-P','16','4',apk],env=env)
        libraries=native_16k(apk)
        badging=b.output([tools/'aapt','dump','badging',apk],env=env)
        if not all(x in badging.splitlines()[0] for x in [f"name='{b.PACKAGE}'",f"versionCode='{number}'",f"versionName='{version}'"]):
            raise ValueError('Store package identity mismatch')
        activity=re.search(r"launchable-activity: name='([^']+)'",badging)
        if not activity: raise ValueError('Launch activity missing')
        qa_env={k:v for k,v in env.items() if k not in {'TM_ORIGINAL_STOREPASS','TM_ORIGINAL_KEYPASS'}}
        qa=b.native_smoke(apk,qa_env,activity[1],'original')
        if b.FAILED_RENEWAL.is_set() or b.latest_source()!=source or b.output(['git','status','--porcelain'],cwd=b.SOURCE_DIR):
            raise ValueError('Lease, source or clean tree changed; no draft upload')
        b.lease('check')
        artifact=b.ROOT/filename;shutil.copyfile(bundle,artifact)
        digest=hashlib.file_digest(artifact.open('rb'),'sha256').hexdigest()
        manifest={'application':'TourMaps GO+','platform':'android','format':'aab','channel':'store-upload-draft',
            'version':version,'build_number':number,'package':b.PACKAGE,'source_commit':source,
            'clean_tree_at_build':True,'builder_run':os.environ['GITHUB_RUN_URL'],
            'notification_summary':changes,'notification_notes_commit':notes_commit,
            'signing':{'signature_verified':True,'certificate_sha256':CHANNELS['original']['cert'],
                       'play_upload_certificate_match':'not-verified'},
            'qa':{'flutter_tests':'passed','node_tests':'passed','analysis_errors':0,
                  'native_permission_policy':'passed','bundletool_validation':True,'zipalign_16k':True,
                  'elf_16k_libraries':libraries,'universal_apk_sha256':hashlib.file_digest(apk.open('rb'),'sha256').hexdigest(),**qa},
            'bundletool':{'version':BUNDLETOOL_VERSION,'sha256':BUNDLETOOL_SHA256},
            'artifact':{'filename':filename,'bytes':artifact.stat().st_size,'sha256':digest},
            'github_release_draft':True,'play_uploaded':False,'physical_qa':False,'whatsapp_sent':False}
        file=b.ROOT/MANIFEST;file.write_text(json.dumps(manifest,indent=2))
        body=b.ROOT/'store-notes.md';body.write_text(f'Fuente: {source}. AAB firmado con la clave original existente. {changes}\n\nBorrador privado para carga posterior. Certificado de carga/versionCode en Play y QA física pendientes. No Google Play, no APK instalable, no envío WhatsApp.')
        b.run('store-draft-create',['gh','release','create',tag,'--repo',b.CHANNEL,'--draft','--prerelease',
            '--target',os.environ['GITHUB_SHA'],'--title',f'TourMaps {version}+{number} - carga Play (borrador)',
            '--notes-file',body],timeout=90)
        b.run('store-draft-upload',['gh','release','upload',tag,artifact,file,'--repo',b.CHANNEL],timeout=240)
        # Read the uploaded draft back through the authorized CLI, never publish it.
        downloaded=b.ROOT/'store-download-check';downloaded.mkdir(mode=0o700)
        b.run('store-draft-download',['gh','release','download',tag,'--repo',b.CHANNEL,'--pattern',filename,'--dir',downloaded],timeout=240)
        if hashlib.file_digest((downloaded/filename).open('rb'),'sha256').hexdigest()!=digest:
            raise ValueError('Stored bundle download differs')
        if b.FAILED_RENEWAL.is_set() or b.latest_source()!=source: raise ValueError('Source advanced; preserve draft only')
        b.lease('check')
        print(json.dumps({'draft_verified':True,'tag':tag,'source':source,'version':f'{version}+{number}',
            'sha256':digest,'bytes':artifact.stat().st_size,'play_uploaded':False,'whatsapp_sent':False}))
    finally:
        b.STOP.set();thread.join(timeout=30)
        for path in private_files:
            with contextlib.suppress(OSError): path.unlink()
        if b.QA_OWNED:
            with contextlib.suppress(Exception): b.lease('release','qa-isolated')
        with contextlib.suppress(Exception): b.lease('release')


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('STOP: '+str(error),file=sys.stderr);raise SystemExit(1)

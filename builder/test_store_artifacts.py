import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

from channels import next_number
from store_artifacts import identity, native_16k, property_value, verify_signed_jar


class StorePolicyTests(unittest.TestCase):
    def test_store_draft_reserves_number_without_entering_apk_delivery_channels(self):
        tag,name=identity('1.0.52',76)
        self.assertEqual(next_number([{'tag_name':tag,'draft':True},{'tag_name':'v1.0.51-tourmaps-pilot75'}]),77)
        self.assertTrue(name.endswith('.aab'))
        for channel in ['pilot','original']:
            self.assertIsNone(re.fullmatch(r'v[0-9.]+-tourmaps-'+channel+r'\d+',tag))

    def test_unreviewable_or_historical_identity_rejected(self):
        for version,number in [('1.0.52',56),('1.0.52',True),('x/1.0.52',76)]:
            with self.assertRaises(ValueError): identity(version,number)

    def test_private_properties_preserve_non_ascii_and_special_characters(self):
        self.assertEqual(property_value('a\\b:=#! \nΩ🐾'),r'a\\b\:\=\#\!\ \n\u03a9\ud83d\udc3e')

    def test_elf_checks_actual_segments_and_rejects_4k_or_truncated_payload(self):
        def elf(alignment):
            raw=bytearray(120);raw[:6]=b'\x7fELF\x02\x01'
            struct.pack_into('<Q',raw,32,64);struct.pack_into('<HH',raw,54,56,1)
            struct.pack_into('<IIQQQQQQ',raw,64,1,5,0,0,0,120,120,alignment)
            return raw
        with tempfile.TemporaryDirectory() as tmp:
            apk=Path(tmp)/'fixture.apk'
            for data,valid in [(elf(16384),True),(elf(4096),False),(b'\x7fELF\x02',False)]:
                with zipfile.ZipFile(apk,'w') as z:z.writestr('lib/arm64-v8a/libfixture.so',data)
                if valid:self.assertEqual(native_16k(apk),1)
                else:
                    with self.assertRaises(ValueError):native_16k(apk)


class SignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        found=shutil.which('jarsigner')
        cls.java_bin=Path(os.environ['STORE_TEST_JAVA_BIN']) if os.environ.get('STORE_TEST_JAVA_BIN') else (Path(found).parent if found else None)
        if cls.java_bin is None:raise unittest.SkipTest('Local JDK unavailable; cloud JDK must execute signature fixtures')
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.key=cls.root/'fixture.jks';cls.alias='fixture'
        cls.env={**os.environ,'TM_ORIGINAL_STOREPASS':'isolated-fixture-only'}
        def run(args):
            r=subprocess.run([str(x) for x in args],env=cls.env,capture_output=True,timeout=60)
            if r.returncode:raise RuntimeError('JDK fixture failed')
            return r.stdout
        run([cls.java_bin/'keytool','-genkeypair','-alias',cls.alias,'-keyalg','RSA','-keysize','2048',
             '-validity','2','-dname','CN=Isolated TourMaps test fixture','-keystore',cls.key,
             '-storepass:env','TM_ORIGINAL_STOREPASS','-keypass:env','TM_ORIGINAL_STOREPASS'])
        cls.bundle=cls.root/'fixture.aab'
        with zipfile.ZipFile(cls.bundle,'w') as z:z.writestr('base/manifest/AndroidManifest.xml',b'isolated-signature-fixture')
        run([cls.java_bin/'jarsigner','-keystore',cls.key,'-storepass:env','TM_ORIGINAL_STOREPASS',cls.bundle,cls.alias])
        cls.digest=hashlib.sha256(run([cls.java_bin/'keytool','-exportcert','-keystore',cls.key,
            '-storepass:env','TM_ORIGINAL_STOREPASS','-alias',cls.alias])).hexdigest()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,'tmp'):cls.tmp.cleanup()

    def test_known_signer_and_all_payload_must_verify(self):
        verify_signed_jar(self.bundle,self.key,self.alias,self.env,self.java_bin,self.digest)
        with self.assertRaises(ValueError):
            verify_signed_jar(self.bundle,self.key,self.alias,self.env,self.java_bin,'0'*64)
        bad=self.root/'unsigned-extra.aab';shutil.copyfile(self.bundle,bad)
        with zipfile.ZipFile(bad,'a') as z:z.writestr('base/dex/unsigned.dex',b'unsigned')
        with self.assertRaises(ValueError):
            verify_signed_jar(bad,self.key,self.alias,self.env,self.java_bin,self.digest)


if __name__=='__main__':unittest.main()

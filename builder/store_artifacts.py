"""Strict checks for a draft AAB; none of these assert Play publication or UAT."""
import re
import struct
import subprocess
import zipfile
from pathlib import Path


def identity(version, number):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or type(number) is not int or number <= 56:
        raise ValueError('Reviewed monotonically increasing store identity required')
    return f'v{version}-tourmaps-store{number}', f'TourMaps-Go-{version}+{number}-store.aab'


def property_value(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Existing signing property required')
    result = ''
    for char in value:
        if char in '\\:=#! ':
            result += '\\' + char
        elif char == '\n': result += '\\n'
        elif char == '\r': result += '\\r'
        elif char == '\t': result += '\\t'
        elif 32 <= ord(char) <= 126: result += char
        else:
            # Properties.load(InputStream) uses ISO-8859-1 and UTF-16 escapes.
            encoded = char.encode('utf-16-be')
            result += ''.join('\\u'+encoded[i:i+2].hex() for i in range(0,len(encoded),2))
    return result


def verify_signed_jar(bundle, keystore, alias, env, java_bin, expected):
    def command(args):
        r = subprocess.run([str(x) for x in args], env=env, capture_output=True, text=True, timeout=60)
        if r.returncode: raise ValueError('Strict AAB signature or payload integrity verification failed')
        return r.stdout
    # The existing pinned certificate is trusted locally for this verification;
    # no public CA, new key, weaker algorithm or unsigned payload exception.
    command([Path(java_bin)/'jarsigner', '-J-Duser.language=en', '-verify', '-strict',
             '-keystore', keystore, '-storepass:env', 'TM_ORIGINAL_STOREPASS', bundle, alias])
    text = command([Path(java_bin)/'keytool', '-J-Duser.language=en', '-printcert', '-jarfile', bundle])
    digests = re.findall(r'SHA256:\s*([A-Fa-f0-9:]+)', text)
    if len(digests) != 1 or digests[0].replace(':','').lower() != expected:
        raise ValueError('AAB signer differs from the existing original certificate')


def native_16k(apk):
    checked = 0
    with zipfile.ZipFile(apk) as archive:
        for name in archive.namelist():
            if not name.startswith(('lib/arm64-v8a/','lib/x86_64/')) or not name.endswith('.so'):
                continue
            raw = archive.read(name)
            if len(raw) < 64 or raw[:5] != b'\x7fELF\x02' or raw[5] not in (1,2):
                raise ValueError('64-bit native library must be a valid ELF64')
            endian = '<' if raw[5] == 1 else '>'
            offset = struct.unpack_from(endian+'Q', raw, 32)[0]
            size, count = struct.unpack_from(endian+'HH', raw, 54)
            if size < 56 or not 0 < count <= 128 or offset+count*size > len(raw):
                raise ValueError('Invalid native program headers')
            loads = 0
            for i in range(count):
                row = struct.unpack_from(endian+'IIQQQQQQ',raw,offset+i*size)
                if row[0] != 1: continue
                loads += 1
                if row[-1] < 16384 or row[-1] & (row[-1]-1) or row[2] % 16384 != row[3] % 16384:
                    raise ValueError('Native library is incompatible with 16 KiB pages')
            if not loads: raise ValueError('Native library has no load segment')
            checked += 1
    if not checked: raise ValueError('No 64-bit native payload verified')
    return checked

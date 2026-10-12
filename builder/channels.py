"""Fixed authorized signing channels and unique monotonically increasing versions."""
import re

PILOT_CERT = '79f0e7b026ef0634ad7b8b7f37fc07f40aac874897efa1ea0e0593bc05a8b8d5'
ORIGINAL_CERT = '263c2fab542e49c0219a35854cd2816a06fca0f99569b031dadf4cc6f735aba4'
CHANNELS = {
    'pilot': {'cert': PILOT_CERT, 'baseline': '1.0.30+54', 'compatible_with': 54,
        'url': 'https://github.com/Ahgarzon/tm-apk/releases/download/v1.0.30-tourmaps-pilot54/TourMaps-Go-1.0.30%2B54-candidata.apk',
        'sha256': 'c1c8b4c00d3e9c2f6b60551f4e498435ff509a1b7f5a8dcb1837d90dfd69ea2d'},
    'original': {'cert': ORIGINAL_CERT, 'baseline': '1.0.31+55', 'compatible_with': 55,
        'url': 'https://github.com/jamesvidaltourmaps/tourmaps-apk/releases/download/v1.0.31-original55/TourMaps-Go-1.0.31-55.apk',
        'sha256': '9ee4ac851370e4d13677ccfdb0372ef6c2d17e635704cf974bde2c008826af5a'},
}


def next_number(releases):
    # +56 was reserved for James' local original candidate before this channel.
    maximum = 56
    for release in releases:
        match = re.fullmatch(r'v[0-9.]+-(?:tourmaps-pilot|tourmaps-original|original)(\d+)', release['tag_name'])
        if match:
            maximum = max(maximum, int(match[1]))
    return maximum+1


def version_name(pubspec, number):
    match = re.search(r'^version:\s*(\d+)\.(\d+)\.(\d+)\+(\d+)\s*$', pubspec, re.M)
    if not match or number <= int(match[4]):
        raise ValueError('Source version must be exact and candidate build strictly newer')
    major, minor, patch, base = map(int, match.groups())
    return f'{major}.{minor}.{patch+number-base}'


def identity(channel, version, number):
    if channel not in CHANNELS:
        raise ValueError('Only explicitly approved signing channels')
    return f'v{version}-tourmaps-{channel}{number}', f'TourMaps-Go-{version}+{number}-{channel}.apk'

"""Fail closed when an Android release still points at the retired shared API."""
from pathlib import Path


def verify_dedicated_api_source(source_dir: Path):
    adapter = source_dir / 'lib/services/tourmaps_api_config.dart'
    if not adapter.is_file():
        raise ValueError('Android source has no reviewed dedicated API adapter')
    config = adapter.read_text(encoding='utf-8')
    if ('TOURMAPS_API_BASE_URL' not in config or
            'https://tourmaps-api-62-171-153-218.sslip.io' not in config):
        raise ValueError('Android source does not select the dedicated HTTPS API')
    for file in (source_dir / 'lib').rglob('*.dart'):
        if 'http://94.72.117.162:3001' in file.read_text(encoding='utf-8'):
            raise ValueError('Android source still contains the retired cleartext API')

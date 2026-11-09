"""Fail-closed Firebase authority defines for the Android event writer and reader."""

import re
import urllib.parse


def android_realtime_defines(firebase):
    project = firebase.get('project_info', {})
    if project.get('project_id') != 'tourmapspopayan':
        raise ValueError('Registered Firebase project required for Android event authority')
    database = urllib.parse.urlsplit(project.get('firebase_url') or '')
    if (database.scheme != 'https' or database.username or database.password or
            database.port or database.query or database.fragment or database.path not in {'', '/'} or
            database.hostname not in {
                'tourmapspopayan-default-rtdb.firebaseio.com',
                'tourmapspopayan-default-rtdb.firebasedatabase.app'}):
        raise ValueError('Registered Firebase database required for Android event authority')
    clients = [client for client in firebase.get('client', []) if
               client.get('client_info', {}).get('android_client_info', {}).get('package_name') ==
               'com.gopluss.tourmapsgo']
    if len(clients) != 1:
        raise ValueError('Exactly one Android Firebase client required')
    keys = [entry.get('current_key') for entry in clients[0].get('api_key', [])]
    keys = [value for value in keys if isinstance(value, str) and re.fullmatch(r'AIza[A-Za-z0-9_-]{35}', value)]
    if len(keys) != 1:
        raise ValueError('Exactly one registered Android Firebase API key required')
    return [
        '--dart-define=TOURMAPS_REALTIME_AUTHORITY_MODE=v2',
        '--dart-define=TOURMAPS_TOURIST_EVENT_V2=true',
        '--dart-define=TOURMAPS_FIREBASE_PROJECT_ID=tourmapspopayan',
        '--dart-define=TOURMAPS_FIREBASE_DATABASE_URL='+database.geturl(),
        '--dart-define=TOURMAPS_FIREBASE_API_KEY='+keys[0],
    ]

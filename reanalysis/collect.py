"""Collect a reproducible snapshot; Python 3.10+, standard library only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = Path(__file__).resolve().parent
QUERIES = {'ja': '川越', 'zh': '川越', 'en': 'kawagoe', 'ko': '가와고에|카와고에'}


def load_key():
    key = os.environ.get('YOUTUBE_API_KEY', '').strip()
    if not key and (BASE / '.env').exists():
        for line in (BASE / '.env').read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == 'YOUTUBE_API_KEY':
                key = value.strip().strip('\"\'')
    if not key or key == 'replace_with_your_key':
        raise RuntimeError('Set YOUTUBE_API_KEY in the environment or local .env file.')
    return key


def api(endpoint, params, key):
    url = 'https://www.googleapis.com/youtube/v3/' + endpoint + '?' + urllib.parse.urlencode(params)
    # Keep credential out of request URLs, saved manifests and errors.
    req = urllib.request.Request(url, headers={'X-Goog-Api-Key': key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code >= 500 and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            try:
                body = json.loads(exc.read())
                reasons = [e.get('reason', 'unknown') for e in body.get('error', {}).get('errors', [])]
            except (ValueError, AttributeError):
                reasons = ['unreadable_response']
            raise RuntimeError(f'YouTube API HTTP {exc.code}: {reasons}') from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise RuntimeError('Network request failed after four attempts.') from None
            time.sleep(2 ** attempt)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def collect(pages):
    key = load_key()
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = BASE / 'runs' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'started_utc': stamp, 'status': 'in_progress', 'pages_per_language': pages,
                'python': sys.version, 'queries': QUERIES, 'category': '19',
                'regionCode': None, 'order': 'relevance', 'published_period': 'unrestricted',
                'language_definition': 'search setting, not verified video/audience language',
                'search_calls': 0, 'video_calls': 0}
    memberships = []
    ids = set()
    try:
        for lang, query in QUERIES.items():
            token = None
            seen_tokens = set()
            lang_ids = set()
            for page in range(pages):
                params = {'part': 'snippet', 'q': query, 'type': 'video', 'maxResults': 50,
                          'videoCategoryId': '19', 'relevanceLanguage': lang, 'order': 'relevance'}
                if token:
                    params['pageToken'] = token
                result = api('search', params, key)
                manifest['search_calls'] += 1
                save(folder / f'search_{lang}_{page+1:02}.json', result)
                for item in result.get('items', []):
                    vid = item.get('id', {}).get('videoId')
                    if vid and vid not in lang_ids:
                        memberships.append({'search_language': lang, 'video_id': vid})
                        lang_ids.add(vid)
                        ids.add(vid)
                token = result.get('nextPageToken')
                if not token or token in seen_tokens:
                    break
                seen_tokens.add(token)
            print(f'{lang}: {len(lang_ids)} unique search results', flush=True)
        save(folder / 'memberships.json', memberships)
        videos = []
        ordered = sorted(ids)
        for offset in range(0, len(ordered), 50):
            result = api('videos', {'part': 'snippet,statistics,contentDetails',
                                   'id': ','.join(ordered[offset:offset+50])}, key)
            manifest['video_calls'] += 1
            save(folder / f'videos_{offset//50+1:03}.json', result)
            retrieved = dt.datetime.now(dt.timezone.utc).isoformat()
            for item in result.get('items', []):
                videos.append({'retrieved_at_utc': retrieved, **item})
        save(folder / 'videos.json', videos)
        manifest.update(status='complete', unique_video_count=len(videos),
                        unavailable_ids=sorted(ids-{v['id'] for v in videos}))
    except Exception:
        manifest['status'] = 'incomplete'
        raise
    finally:
        manifest['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest['sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in folder.glob('*.json') if p.name != 'manifest.json'}
        save(folder / 'manifest.json', manifest)
        print(f'Snapshot: {folder}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pages', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.pages <= 10:
        parser.error('--pages must be 1..10')
    try:
        collect(args.pages)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

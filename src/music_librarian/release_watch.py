"""Weekly Qobuz release metadata digest. Never downloads or changes music."""
import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import json
import re
import subprocess
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from .qobuz_auth import atomic_json

STATE = Path.home() / '.local/state/qobuz-release-watch'
GWS = Path.home() / 'Repos/index/scripts/gws-safe.sh'
RECIPIENT = 'shea.conaway@gmail.com'
EXCLUSIONS = Path(__file__).with_name('release_exclusions.json')


def excluded_artist_ids():
    return set(json.loads(EXCLUSIONS.read_text())['artists'])


def has_excluded_artist(album, excluded):
    # Main credits matter; a guest appearance does not retire an active artist.
    credits = [album.get('artist') or {}]
    credits += [a for a in album.get('artists') or [] if 'main-artist' in (a.get('roles') or [])]
    return any(str(a.get('id')) in excluded for a in credits)


def is_archival_release(album):
    """Use explicit tags plus edition/title markers, never free-form descriptions."""
    tags = album.get('release_tags') or []
    metadata = ' '.join(str(album.get(k) or '') for k in ('version', 'recording_information'))
    markers = r'\b(live|compilation|reissue|remaster(?:ed)?|anthology|retrospective|anniversary)\b'
    if any(re.search(markers, str(tag), re.I) for tag in tags) or re.search(markers, metadata, re.I):
        return True
    if any(album.get(k) is True for k in ('is_live', 'is_compilation', 'is_reissue')):
        return True
    title = album.get('title') or ''
    return bool(re.search(
        r'\b(?:reissue|remaster(?:ed)?|anniversary|compilation|anthology|retrospective|'
        r'greatest hits|best of|complete recordings|singles collection|box set)\b|'
        r'\b(?:in concert|unplugged)\b|^live$|^live (?:at|in|from|on)\b|'
        r'[(\[:–—-]\s*live\b|\blive\s*$', title, re.I))


def release_key(album):
    """Match editions of the same work, keeping distinct artists separate."""
    title = re.sub(r'\s*[\[(][^\])]*(?:deluxe|remaster|expanded|anniversary|edition)[^\])]*[\])]', '', album['title'], flags=re.I)
    title = re.sub(r'\s+', ' ', title).strip().casefold()
    artist = str(album.get('artist', {}).get('id', ''))
    return artist + '|' + title


def is_full_album(album):
    return str(album.get('release_type') or album.get('product_type') or '').lower() == 'album'


def is_classical(album):
    """Qobuz genre 10 includes classical and its nested subgenres."""
    genre = album.get('genre') or {}
    return (str(genre.get('id')) == '10'
            or any(str(parent) == '10' for parent in genre.get('path') or [])
            or str(genre.get('name', '')).casefold() == 'classical'
            or genre.get('slug') == 'classique')


def select_releases(albums, since, today, delivered, excluded=None):
    excluded = excluded_artist_ids() if excluded is None else excluded
    groups = {}
    earliest = {}
    for album in albums:
        if not is_full_album(album):
            continue
        try:
            date = dt.date.fromisoformat(album.get('release_date_original', ''))
        except (ValueError, TypeError):
            continue
        key = release_key(album)
        earliest[key] = min(earliest.get(key, date), date)
    for album in albums:
        if (not is_full_album(album) or is_classical(album) or album.get('streamable') is False
                or has_excluded_artist(album, excluded) or is_archival_release(album)):
            continue
        raw_date = album.get('release_date_original', '')
        try:
            date = dt.date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            continue
        key = release_key(album)
        if not since <= date <= today or earliest[key] < since or key in delivered:
            continue
        old = groups.get(key)
        fidelity = lambda a: (a.get('maximum_bit_depth') or 0, a.get('maximum_sampling_rate') or 0)
        if old is None or fidelity(album) > fidelity(old):
            groups[key] = album
    return sorted(groups.values(), key=lambda a: (a['release_date_original'], a.get('artist', {}).get('name', ''), a['title']), reverse=True)


def render(releases, artist_count, since, today):
    lines = [f'Qobuz new releases: {since} through {today}',
             f'Checked {artist_count} artists from your Qobuz library.', '']
    if not releases:
        lines.append('No new releases found this week.')
    for album in releases:
        artist = album.get('artist', {}).get('name', 'Unknown artist')
        kind = album.get('release_type') or album.get('product_type') or f"{album.get('tracks_count', '?')} tracks"
        lines.extend([f"{artist} — {album['title']}",
                      f"{album['release_date_original']} · {kind}",
                      f"https://play.qobuz.com/album/{album['id']}", ''])
    lines += ['', 'New studio albums only; deceased artists, inactive bands, live albums, compilations, reissues, remasters, classical music (including its subgenres), singles, EPs, and unclassified releases are excluded. Artist exclusions use a reviewed local list. Dates and release metadata come from Qobuz; unmarked archival releases or incorrect catalog metadata may still slip through.']
    return '\n'.join(lines)


def gmail(operation, params, body=None):
    command = [str(GWS), 'gmail', 'users', 'messages', operation, '--params', json.dumps(params)]
    if body is not None:
        command += ['--json', json.dumps(body)]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        if result.returncode:
            raise RuntimeError('Gmail operation failed')
        data = json.loads(result.stdout)
        if 'error' in data:
            raise RuntimeError('Gmail operation failed')
        return data
    except (subprocess.TimeoutExpired, ValueError):
        raise RuntimeError('Gmail response could not be confirmed') from None


def deliver(state_dir, pending):
    """An uncertain send is reconciled, never blindly repeated."""
    message_id = pending['message_id']
    found = gmail('list', {'userId': 'me', 'q': f'in:anywhere rfc822msgid:{message_id}', 'includeSpamTrash': True})
    if found.get('messages'):
        return found['messages'][0]['id']
    if pending.get('attempted'):
        raise RuntimeError('Previous email delivery is uncertain. Inspect pending.json and Gmail before retrying.')
    pending['attempted'] = True
    atomic_json(state_dir / 'pending.json', pending)
    message = EmailMessage()
    message['To'] = RECIPIENT
    message['From'] = RECIPIENT
    message['Subject'] = pending['subject']
    message['Message-ID'] = '<' + message_id + '>'
    message.set_content(pending['body'])
    response = gmail('send', {'userId': 'me'}, {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()})
    if not response.get('id'):
        raise RuntimeError('Email delivery could not be confirmed; pending state retained')
    return response['id']


def run(state_dir=STATE, preview=False):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / 'lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Release digest is already running') from None
        state_path, pending_path = state_dir / 'state.json', state_dir / 'pending.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {'delivered': [], 'through': None}
        today = dt.datetime.now(ZoneInfo('America/New_York')).date()
        if not preview and not pending_path.exists() and state['through'] == str(today):
            print('Already delivered today', flush=True)
            return
        if pending_path.exists() and not preview:
            pending = json.loads(pending_path.read_text())
        else:
            since = dt.date.fromisoformat(state['through']) - dt.timedelta(days=7) if state['through'] else today - dt.timedelta(days=7)
            collector = Path(__file__).resolve().parents[2] / 'tools/qobuz/collect.mjs'
            snapshot_path = state_dir / 'catalog.json'
            subprocess.run(['node', str(collector), '--output', str(snapshot_path), '--since', str(since), '--through', str(today)], check=True, timeout=1800)
            snapshot = json.loads(snapshot_path.read_text())
            artists, albums = snapshot['artists'], snapshot['albums']
            releases = select_releases(albums, since, today, set(state['delivered']))
            body = render(releases, len(artists), since, today)
            digest_id = hashlib.sha256((str(today) + body).encode()).hexdigest()[:24]
            pending = {'subject': f'Qobuz weekly releases — {today}', 'body': body,
                       'message_id': f'qobuz-{digest_id}@index.local', 'through': str(today),
                       'keys': [release_key(a) for a in releases], 'artists': len(artists)}
            atomic_json(state_dir / 'preview.json', pending)
            print(body, flush=True)
            if preview:
                return
            if state['through'] == str(today):
                print('Already delivered today', flush=True)
                return
            atomic_json(pending_path, pending)
        message_id = deliver(state_dir, pending)
        atomic_json(state_path, {'through': pending['through'], 'delivered': sorted(set(state['delivered']) | set(pending['keys'])), 'gmail_message_id': message_id, 'artists': pending['artists']})
        pending_path.unlink()
        print('Digest delivered and recorded.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='Read Qobuz and write a preview; do not email or advance state')
    parser.add_argument('--state-dir', type=Path, default=STATE)
    args = parser.parse_args()
    try:
        run(args.state_dir, args.preview)
    except Exception as error:
        # Avoid traceback URLs/headers containing auth tokens.
        print(f'Digest failed: {error if isinstance(error, RuntimeError) else type(error).__name__}', flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()

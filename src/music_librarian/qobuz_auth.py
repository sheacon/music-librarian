"""Browser OAuth for Qobuz metadata access; secrets stay in a local 0600 file."""
import configparser
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTH_PATH = Path.home() / '.config/music-librarian/qobuz-auth.json'
CONFIG_PATH = Path.home() / '.config/qobuz-dl/config.ini'
API = 'https://www.qobuz.com/api.json/0.2/'
# Qobuz web sign-in callback parameter, documented by the qobine client.
CALLBACK_KEY = '6lz8C03UDIC7'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def login(destination=AUTH_PATH):
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    app_id = config['DEFAULT']['app_id']
    callback_path = '/callback/' + secrets.token_urlsafe(24)
    outcome = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log a callback code or credentials.

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != callback_path:
                self.send_error(404)
                return
            code = urllib.parse.parse_qs(parsed.query).get('code_autorisation', [''])[0]
            if not code:
                self.send_error(400, 'Missing authorization code')
                return
            try:
                query = urllib.parse.urlencode({'code': code, 'private_key': CALLBACK_KEY})
                request = urllib.request.Request(API + 'oauth/callback?' + query,
                    headers={'X-App-Id': app_id, 'User-Agent': 'MusicLibrarian/0.1'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.load(response)
                if not data.get('token'):
                    raise ValueError('No token returned')
                atomic_json(destination, {'app_id': app_id, 'token': data['token']})
                outcome['success'] = True
                message = 'Qobuz connected. You can close this tab.'
                self.send_response(200)
            except Exception:
                outcome['error'] = True
                message = 'Qobuz sign-in could not be completed. No credentials were saved.'
                self.send_response(502)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(message.encode())

    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        callback = f'http://127.0.0.1:{server.server_port}{callback_path}'
        url = 'https://www.qobuz.com/signin/oauth?' + urllib.parse.urlencode(
            {'ext_app_id': app_id, 'redirect_url': callback})
        print('Open this Qobuz sign-in URL:', flush=True)
        print(url, flush=True)
        deadline = time.monotonic() + 600
        server.timeout = 1
        while not outcome and time.monotonic() < deadline:
            server.handle_request()
    if not outcome.get('success'):
        raise SystemExit('Sign-in did not complete.')
    print('Qobuz authentication saved securely.', flush=True)


if __name__ == '__main__':
    login()

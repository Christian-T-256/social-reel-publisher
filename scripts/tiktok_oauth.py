#!/usr/bin/env python3
"""Run TikTok desktop OAuth with PKCE and save private rotating credentials."""

import hashlib
import http.server
import json
import os
import secrets
import string
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reel_publisher.io_utils import save_private_json

AUTHORIZE = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "user.info.basic,video.upload"
ALLOWED = string.ascii_letters + string.digits + "-._~"


class Callback(http.server.BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self):
        values = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        for key in ("code", "state", "error", "error_description"):
            if values.get(key):
                self.result[key] = values[key][0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authorization received. You may close this tab.")

    def log_message(self, *_args):
        return


def main() -> int:
    secrets_raw = os.environ.get("SOCIAL_PUBLISHER_SECRETS_DIR", "")
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    port = int(os.environ.get("TIKTOK_REDIRECT_PORT", "8765"))
    if not secrets_raw or not client_key or not client_secret:
        sys.exit(
            "set SOCIAL_PUBLISHER_SECRETS_DIR, TIKTOK_CLIENT_KEY, and TIKTOK_CLIENT_SECRET"
        )
    redirect = f"http://localhost:{port}/"
    verifier = "".join(secrets.choice(ALLOWED) for _ in range(64))
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    state = secrets.token_hex(16)
    server = http.server.HTTPServer(("localhost", port), Callback)
    threading.Thread(target=server.handle_request, daemon=True).start()
    url = AUTHORIZE + "?" + urllib.parse.urlencode(
        {
            "client_key": client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": redirect,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    print(f"Register this redirect URI in the developer portal: {redirect}")
    webbrowser.open(url)
    for _ in range(150):
        if Callback.result:
            break
        time.sleep(2)
    if Callback.result.get("error"):
        sys.exit("TikTok authorization was cancelled")
    if Callback.result.get("state") != state or not Callback.result.get("code"):
        sys.exit("TikTok authorization timed out or returned an invalid state")
    try:
        response = requests.post(
            TOKEN,
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "code": Callback.result["code"],
                "grant_type": "authorization_code",
                "redirect_uri": redirect,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SystemExit("TikTok token exchange failed") from exc
    if not body.get("access_token"):
        sys.exit("TikTok rejected the token exchange")
    now = time.time()
    save_private_json(
        Path(secrets_raw).expanduser().resolve() / "tiktok.json",
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "access_token": body["access_token"],
            "refresh_token": body.get("refresh_token", ""),
            "expires_at": now + int(body.get("expires_in", 86400)),
            "refresh_expires_at": now + int(body.get("refresh_expires_in", 31536000)),
            "initial_auth_at": now,
            "open_id_at_authorization": body.get("open_id", ""),
        },
    )
    print("TikTok OAuth complete. Run --pin tiktok after checking the selected account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

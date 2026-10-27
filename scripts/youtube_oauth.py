#!/usr/bin/env python3
"""Authorize YouTube with upload and identity scopes, then save a private token."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reel_publisher.io_utils import save_private_json
from reel_publisher.platforms.youtube import SCOPES


def main() -> int:
    secrets_raw = os.environ.get("SOCIAL_PUBLISHER_SECRETS_DIR", "")
    client_raw = os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "")
    if not secrets_raw or not client_raw:
        sys.exit(
            "set SOCIAL_PUBLISHER_SECRETS_DIR and YOUTUBE_CLIENT_SECRETS_FILE before authorizing"
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SystemExit("install requirements.txt before running this helper") from exc
    client_path = Path(client_raw).expanduser().resolve()
    if not client_path.is_file():
        sys.exit("YOUTUBE_CLIENT_SECRETS_FILE does not point to a readable file")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    credentials = flow.run_local_server(port=0, prompt="select_account consent")
    save_private_json(
        Path(secrets_raw).expanduser().resolve() / "youtube_token.json",
        json.loads(credentials.to_json()),
    )
    print("YouTube OAuth complete. Run --pin youtube after checking the selected channel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

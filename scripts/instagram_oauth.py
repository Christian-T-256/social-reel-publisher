#!/usr/bin/env python3
"""Validate and save an Instagram Login access token without echoing it."""

import argparse
import getpass
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reel_publisher.io_utils import load_json, save_private_json


GRAPH = "https://graph.instagram.com/v25.0"


def validate(token: str) -> dict:
    try:
        response = requests.get(
            f"{GRAPH}/me",
            params={"fields": "user_id,username", "access_token": token},
            timeout=30,
        )
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SystemExit("could not validate the Instagram token") from exc
    account_id = body.get("user_id") or body.get("id")
    if response.status_code >= 400 or body.get("error") or not account_id:
        sys.exit("Instagram rejected the token")
    return {"account_id": str(account_id), "username": str(body.get("username", ""))}


def main() -> int:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--save", action="store_true", help="validate and save a new token")
    actions.add_argument("--refresh", action="store_true", help="refresh the saved long-lived token")
    actions.add_argument("--status", action="store_true", help="show token age and saved identity")
    args = parser.parse_args()
    secrets_raw = os.environ.get("SOCIAL_PUBLISHER_SECRETS_DIR", "")
    if not secrets_raw:
        sys.exit("set SOCIAL_PUBLISHER_SECRETS_DIR to a brand-specific folder")
    path = Path(secrets_raw).expanduser().resolve() / "instagram.json"

    if args.status:
        saved = load_json(path)
        age_days = (time.time() - float(saved.get("saved_at", 0))) / 86400
        print(f"Instagram token account: @{saved.get('username_at_authorization', '')}")
        print(f"Instagram token age: {age_days:.1f} days")
        return 0

    if args.refresh:
        saved = load_json(path)
        token = str(saved.get("access_token", ""))
        if not token:
            sys.exit("instagram.json has no access_token")
        try:
            response = requests.get(
                "https://graph.instagram.com/refresh_access_token",
                params={"grant_type": "ig_refresh_token", "access_token": token},
                timeout=30,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise SystemExit("could not refresh the Instagram token") from exc
        if response.status_code >= 400 or body.get("error") or not body.get("access_token"):
            sys.exit("Instagram rejected the token refresh")
        identity = validate(str(body["access_token"]))
        saved.update(
            {
                "access_token": body["access_token"],
                "account_id_at_authorization": identity["account_id"],
                "username_at_authorization": identity["username"],
                "saved_at": time.time(),
            }
        )
        save_private_json(path, saved)
        print(f"Instagram token refreshed for @{identity['username']} [{identity['account_id']}].")
        return 0

    token = getpass.getpass("Paste the Instagram Login access token: ").strip()
    if not token:
        sys.exit("no token entered")
    identity = validate(token)
    save_private_json(
        path,
        {
            "access_token": token,
            "account_id_at_authorization": identity["account_id"],
            "username_at_authorization": identity["username"],
            "saved_at": time.time(),
        },
    )
    print(
        f"Instagram OAuth token saved for @{identity['username']} [{identity['account_id']}]. "
        "Run --pin instagram after checking the account."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .demo import run_demo
from .errors import PublisherError
from .guardrails import PinStore
from .io_utils import load_json
from .models import Media
from .publisher import Publisher


KNOWN_PLATFORMS = ("youtube", "instagram", "tiktok")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish one reviewed vertical video with destination pinning."
    )
    parser.add_argument("--dry-run", action="store_true", help="run the offline mocked flow")
    parser.add_argument(
        "--scenario", choices=("all", "happy", "wrong-account"), default="all",
        help="mock scenario used with --dry-run",
    )
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--platforms", default=",".join(KNOWN_PLATFORMS))
    parser.add_argument("--file", help="local MP4 for YouTube")
    parser.add_argument("--url", help="public MP4 URL for Instagram and TikTok")
    parser.add_argument("--title", default="")
    parser.add_argument("--caption", default="")
    parser.add_argument("--confirm", action="store_true", help="perform live API writes")
    parser.add_argument("--verify", action="store_true", help="check token identities against pins")
    parser.add_argument("--pin", choices=KNOWN_PLATFORMS, help="explicitly pin one live account")
    parser.add_argument("--results-json", help="write a non-secret result ledger")
    return parser


def _names(value: str) -> list[str]:
    names = [item.strip().lower() for item in value.split(",") if item.strip()]
    unknown = sorted(set(names) - set(KNOWN_PLATFORMS))
    if unknown:
        raise PublisherError(f"unknown platforms: {', '.join(unknown)}")
    if not names:
        raise PublisherError("select at least one platform")
    return names


def _secrets_dir() -> Path:
    raw = os.environ.get("SOCIAL_PUBLISHER_SECRETS_DIR", "")
    if not raw:
        raise PublisherError(
            "SOCIAL_PUBLISHER_SECRETS_DIR is required for live use; use a separate folder per brand"
        )
    return Path(raw).expanduser().resolve()


def _platform(name: str, secrets: Path, config: dict):
    from .platforms import InstagramPlatform, TikTokPlatform, YouTubePlatform

    section = config.get(name, {})
    if not isinstance(section, dict):
        raise PublisherError(f"config section {name} must be an object")
    if name == "youtube":
        return YouTubePlatform(
            secrets,
            privacy=str(section.get("privacy", "unlisted")),
            category_id=str(section.get("category_id", "22")),
            timeout=float(section.get("processing_timeout_seconds", 600)),
        )
    if name == "instagram":
        return InstagramPlatform(
            secrets,
            api_version=str(section.get("api_version", "v25.0")),
            timeout=float(section.get("processing_timeout_seconds", 600)),
        )
    return TikTokPlatform(
        secrets,
        timeout=float(section.get("delivery_timeout_seconds", 180)),
    )


def _print_plan(names: list[str], media: Media) -> None:
    print("REVIEW PLAN")
    print(f"  platforms: {', '.join(names)}")
    print(f"  title: {media.title}")
    print(f"  caption: {media.caption[:220]}")
    print(f"  local file: {media.local_file or '(none)'}")
    print(f"  public URL: {media.public_url or '(none)'}")


def _write_results(path: str, results) -> None:
    value = {
        result.platform: {
            "ok": True,
            "artifact_id": result.artifact_id,
            "terminal_state": result.terminal_state,
            "destination_id": result.destination.account_id,
            "url": result.public_url,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        for result in results
    }
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.dry_run:
        try:
            run_demo(args.scenario)
            return 0
        except (PublisherError, AssertionError) as exc:
            print(f"DRY RUN FAILED: {exc}", file=sys.stderr)
            return 1

    try:
        names = _names(args.platforms)
        config = load_json(Path(args.config))
        secrets = _secrets_dir()
        pins = PinStore(secrets / "destination_pins.json")

        if args.pin:
            client = _platform(args.pin, secrets, config)
            identity = client.resolve_destination()
            pins.set(args.pin, identity)
            print(f"PINNED {args.pin}: {identity.display_name} [{identity.account_id}]")
            return 0

        platforms = [_platform(name, secrets, config) for name in names]
        publisher = Publisher(pins)
        if args.verify:
            for platform in platforms:
                publisher.verify(platform)
            return 0

        media = Media(args.title, args.caption, args.file, args.url)
        _print_plan(names, media)
        if not args.confirm:
            print("REVIEW ONLY: no API writes made. Add --confirm to publish.")
            return 0
        if not media.title:
            raise PublisherError("--title is required for a live publish")
        results = publisher.publish_all(platforms, media)
        if args.results_json:
            _write_results(args.results_json, results)
        return 0
    except PublisherError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

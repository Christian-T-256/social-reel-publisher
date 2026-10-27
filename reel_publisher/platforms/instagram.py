from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from ..base import Log, Platform
from ..errors import ConfigurationError, DeliveryError
from ..io_utils import load_json
from ..models import Identity, Media, Receipt, Submission


class InstagramPlatform(Platform):
    name = "instagram"

    def __init__(
        self,
        secrets_dir: Path,
        api_version: str = "v25.0",
        poll_interval: float = 5,
        timeout: float = 600,
        sleep: Callable[[float], None] = time.sleep,
        session: requests.Session | None = None,
    ):
        credentials = load_json(secrets_dir / "instagram.json")
        self.token = str(credentials.get("access_token", ""))
        if not self.token:
            raise ConfigurationError("instagram.json has no access_token")
        self.base = f"https://graph.instagram.com/{api_version}"
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep
        self.http = session or requests.Session()

    @staticmethod
    def _safe_error(data: Any, status: int) -> DeliveryError:
        message = "request rejected"
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or message)
        return DeliveryError(f"Instagram API error (HTTP {status}): {message}")

    def _request(self, method: str, path: str, *, data: dict | None = None, params: dict | None = None) -> dict:
        payload = dict(data or {})
        query = dict(params or {})
        target = payload if method == "POST" else query
        target["access_token"] = self.token
        for attempt in range(3):
            try:
                response = self.http.request(
                    method, f"{self.base}/{path.lstrip('/')}", data=payload or None,
                    params=query or None, timeout=60,
                )
                body = response.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt == 2:
                    raise DeliveryError("Instagram API could not be reached or returned invalid JSON") from exc
                self.sleep(2**attempt)
                continue
            if not isinstance(body, dict):
                raise DeliveryError("Instagram API returned an unexpected JSON shape")
            if response.status_code < 400 and not body.get("error"):
                return body
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise self._safe_error(body, response.status_code)
            self.sleep(2**attempt)
        raise DeliveryError("Instagram API retries exhausted")

    def resolve_destination(self) -> Identity:
        data = self._request("GET", "me", params={"fields": "user_id,username"})
        account_id = data.get("user_id") or data.get("id")
        if not account_id:
            raise DeliveryError("Instagram API did not identify the authorized account")
        return Identity(str(account_id), str(data.get("username", "")))

    def start_publish(self, media: Media, log: Log) -> Submission:
        if not media.public_url:
            raise ConfigurationError("Instagram requires a public video URL")
        identity = self.resolve_destination()
        data = self._request(
            "POST",
            f"{identity.account_id}/media",
            data={
                "media_type": "REELS",
                "video_url": media.public_url,
                "caption": media.caption[:2200],
                "share_to_feed": "true",
            },
        )
        container_id = data.get("id")
        if not container_id:
            raise DeliveryError("Instagram accepted the request without a container id")
        return Submission(str(container_id), "CONTAINER_CREATED", {"account_id": identity.account_id})

    def wait_for_terminal(self, submission: Submission, log: Log) -> Receipt:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            data = self._request(
                "GET", submission.artifact_id, params={"fields": "status_code,status"}
            )
            state = str(data.get("status_code", "UNKNOWN"))
            log(f"[instagram] POLL state={state}")
            if state == "FINISHED":
                published = self._request(
                    "POST",
                    f"{submission.metadata['account_id']}/media_publish",
                    data={"creation_id": submission.artifact_id},
                )
                media_id = published.get("id")
                if not media_id:
                    raise DeliveryError("Instagram publish returned no media id")
                return Receipt(str(media_id), "FINISHED")
            if state in {"ERROR", "EXPIRED"}:
                detail = str(data.get("status", state))[:300]
                raise DeliveryError(f"Instagram container reached {state}: {detail}")
            self.sleep(self.poll_interval)
        raise DeliveryError("Instagram container did not reach FINISHED before the timeout")

    def resolve_landed_destination(self, receipt: Receipt) -> Identity:
        media = self._request(
            "GET", receipt.artifact_id, params={"fields": "username,permalink"}
        )
        identity = self.resolve_destination()
        landed_name = str(media.get("username", ""))
        if landed_name and identity.display_name and landed_name != identity.display_name:
            raise DeliveryError(
                f"Instagram media owner @{landed_name} differs from the authorized account "
                f"@{identity.display_name}"
            )
        receipt.public_url = media.get("permalink")
        return identity

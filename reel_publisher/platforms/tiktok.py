from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from ..base import Log, Platform
from ..errors import ConfigurationError, DeliveryError
from ..io_utils import load_json, save_private_json
from ..models import Identity, Media, Receipt, Submission


API = "https://open.tiktokapis.com/v2"
DELIVERED = {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}
IN_FLIGHT = {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD"}


class TikTokPlatform(Platform):
    name = "tiktok"

    def __init__(
        self,
        secrets_dir: Path,
        poll_interval: float = 5,
        timeout: float = 180,
        sleep: Callable[[float], None] = time.sleep,
        session: requests.Session | None = None,
    ):
        self.path = secrets_dir / "tiktok.json"
        self.credentials = load_json(self.path)
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep
        self.http = session or requests.Session()
        self._ensure_fresh()

    @staticmethod
    def _api_error(body: Any, label: str) -> None:
        error = body.get("error", {}) if isinstance(body, dict) else {}
        code = error.get("code")
        if code not in (None, "", "ok"):
            message = str(error.get("message") or code)[:300]
            raise DeliveryError(f"TikTok {label} failed: {message}")

    def _ensure_fresh(self) -> None:
        initial = self.credentials.get("initial_auth_at")
        if initial and time.time() - float(initial) >= 365 * 86400:
            raise ConfigurationError("TikTok authorization is one year old; run the OAuth helper again")
        expires = float(self.credentials.get("expires_at", 0))
        if self.credentials.get("access_token") and time.time() < expires - 120:
            return
        refresh = self.credentials.get("refresh_token")
        if not refresh:
            raise ConfigurationError("tiktok.json has no usable access_token or refresh_token")
        try:
            response = self.http.post(
                f"{API}/oauth/token/",
                data={
                    "client_key": self.credentials.get("client_key", ""),
                    "client_secret": self.credentials.get("client_secret", ""),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DeliveryError("TikTok token refresh failed without a usable response") from exc
        if not body.get("access_token"):
            raise DeliveryError("TikTok token refresh was rejected; reauthorize the account")
        self.credentials.update(
            {
                "access_token": body["access_token"],
                "refresh_token": body.get("refresh_token", refresh),
                "expires_at": time.time() + int(body.get("expires_in", 86400)),
            }
        )
        if body.get("open_id"):
            self.credentials["open_id"] = body["open_id"]
        if body.get("refresh_expires_in"):
            self.credentials["refresh_expires_at"] = time.time() + int(body["refresh_expires_in"])
        save_private_json(self.path, self.credentials)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credentials['access_token']}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def resolve_destination(self) -> Identity:
        try:
            response = self.http.get(
                f"{API}/user/info/",
                params={"fields": "open_id,display_name"},
                headers={"Authorization": self.headers["Authorization"]},
                timeout=30,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DeliveryError("TikTok account identity could not be resolved") from exc
        if response.status_code >= 400:
            raise DeliveryError(f"TikTok identity check failed with HTTP {response.status_code}")
        self._api_error(body, "identity check")
        user = body.get("data", {}).get("user", {})
        if not user.get("open_id"):
            raise DeliveryError("TikTok identity response contained no open_id")
        return Identity(str(user["open_id"]), str(user.get("display_name", "")))

    def start_publish(self, media: Media, log: Log) -> Submission:
        if not media.public_url:
            raise ConfigurationError("TikTok PULL_FROM_URL requires a public video URL")
        try:
            response = self.http.post(
                f"{API}/post/publish/inbox/video/init/",
                json={"source_info": {"source": "PULL_FROM_URL", "video_url": media.public_url}},
                headers=self.headers,
                timeout=60,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DeliveryError("TikTok upload initialization failed") from exc
        if response.status_code >= 400:
            raise DeliveryError(
                f"TikTok upload initialization failed with HTTP {response.status_code}"
            )
        self._api_error(body, "upload initialization")
        publish_id = body.get("data", {}).get("publish_id")
        if not publish_id:
            raise DeliveryError("TikTok returned no publish_id")
        return Submission(str(publish_id), "ACCEPTED")

    def wait_for_terminal(self, submission: Submission, log: Log) -> Receipt:
        deadline = time.monotonic() + self.timeout
        last = "UNKNOWN"
        while time.monotonic() < deadline:
            try:
                response = self.http.post(
                    f"{API}/post/publish/status/fetch/",
                    json={"publish_id": submission.artifact_id},
                    headers=self.headers,
                    timeout=30,
                )
                body = response.json()
            except (requests.RequestException, ValueError):
                self.sleep(self.poll_interval)
                continue
            if response.status_code >= 400:
                raise DeliveryError(
                    f"TikTok delivery status failed with HTTP {response.status_code}"
                )
            self._api_error(body, "delivery status")
            data = body.get("data", {})
            last = str(data.get("status", "UNKNOWN"))
            log(f"[tiktok] POLL state={last}")
            if last in DELIVERED:
                return Receipt(submission.artifact_id, last)
            if last == "FAILED":
                reason = str(data.get("fail_reason", "no reason returned"))[:300]
                raise DeliveryError(f"TikTok processing failed: {reason}")
            if last not in IN_FLIGHT:
                raise DeliveryError(f"TikTok returned unexpected state: {last}")
            self.sleep(self.poll_interval)
        raise DeliveryError(
            f"TikTok delivery remained {last}; delivery is unconfirmed, so this run is not successful"
        )

    def resolve_landed_destination(self, receipt: Receipt) -> Identity:
        return self.resolve_destination()

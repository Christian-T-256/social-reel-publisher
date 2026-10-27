import time
from collections.abc import Callable
from pathlib import Path

from ..base import Log, Platform
from ..errors import ConfigurationError, DeliveryError
from ..models import Identity, Media, Receipt, Submission


SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
)


class YouTubePlatform(Platform):
    name = "youtube"

    def __init__(
        self,
        secrets_dir: Path,
        privacy: str = "unlisted",
        category_id: str = "22",
        poll_interval: float = 5,
        timeout: float = 600,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.token_path = secrets_dir / "youtube_token.json"
        if not self.token_path.exists():
            raise ConfigurationError("missing youtube_token.json; run the YouTube OAuth helper")
        if privacy not in {"private", "unlisted", "public"}:
            raise ConfigurationError("YouTube privacy must be private, unlisted, or public")
        self.privacy = privacy
        self.category_id = category_id
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep
        self.service = self._build_service()

    def _build_service(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ConfigurationError("install requirements.txt to use YouTube") from exc
        try:
            credentials = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self.token_path.write_text(credentials.to_json(), encoding="utf-8")
                self.token_path.chmod(0o600)
            if not credentials.valid:
                raise ConfigurationError("YouTube token is invalid; run the OAuth helper again")
            return build("youtube", "v3", credentials=credentials, cache_discovery=False)
        except ConfigurationError:
            raise
        except Exception as exc:
            raise DeliveryError("YouTube credentials could not be loaded or refreshed") from exc

    def resolve_destination(self) -> Identity:
        try:
            body = self.service.channels().list(part="id,snippet", mine=True).execute()
        except Exception as exc:
            raise DeliveryError("YouTube could not resolve the channel selected by this token") from exc
        items = body.get("items", [])
        if not items:
            raise DeliveryError("YouTube returned no channel for this token")
        return Identity(str(items[0]["id"]), str(items[0].get("snippet", {}).get("title", "")))

    def start_publish(self, media: Media, log: Log) -> Submission:
        if not media.local_file:
            raise ConfigurationError("YouTube requires a local video file")
        path = Path(media.local_file)
        if not path.is_file():
            raise ConfigurationError(f"YouTube video file does not exist: {path}")
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise ConfigurationError("install requirements.txt to use YouTube") from exc
        description = media.caption
        if "#shorts" not in f"{media.title} {description}".lower():
            description = f"{description}\n\n#Shorts".strip()
        body = {
            "snippet": {
                "title": (media.title or "Short video")[:100],
                "description": description[:5000],
                "categoryId": self.category_id,
            },
            "status": {"privacyStatus": self.privacy, "selfDeclaredMadeForKids": False},
        }
        try:
            request = self.service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(str(path), chunksize=-1, resumable=True),
            )
            response = None
            while response is None:
                progress, response = request.next_chunk()
                if progress:
                    log(f"[youtube] UPLOAD progress={int(progress.progress() * 100)}%")
        except Exception as exc:
            raise DeliveryError("YouTube upload failed") from exc
        video_id = response.get("id")
        if not video_id:
            raise DeliveryError("YouTube accepted the upload without a video id")
        return Submission(str(video_id), "UPLOAD_ACCEPTED", {"insert": response})

    def wait_for_terminal(self, submission: Submission, log: Log) -> Receipt:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                body = self.service.videos().list(
                    part="snippet,status,processingDetails", id=submission.artifact_id
                ).execute()
            except Exception as exc:
                raise DeliveryError("YouTube processing status could not be read") from exc
            items = body.get("items", [])
            if not items:
                raise DeliveryError("YouTube could not find the uploaded video")
            item = items[0]
            state = str(item.get("processingDetails", {}).get("processingStatus", "unknown"))
            log(f"[youtube] POLL state={state}")
            if state == "succeeded":
                actual_privacy = item.get("status", {}).get("privacyStatus")
                if actual_privacy != self.privacy:
                    raise DeliveryError(
                        f"YouTube changed privacy from {self.privacy} to {actual_privacy}; review the upload"
                    )
                return Receipt(
                    submission.artifact_id,
                    state,
                    f"https://youtu.be/{submission.artifact_id}",
                    {"video": item},
                )
            if state in {"failed", "rejected", "terminated"}:
                raise DeliveryError(f"YouTube processing reached terminal failure: {state}")
            self.sleep(self.poll_interval)
        raise DeliveryError("YouTube processing did not reach succeeded before the timeout")

    def resolve_landed_destination(self, receipt: Receipt) -> Identity:
        item = receipt.metadata.get("video", {})
        account_id = item.get("snippet", {}).get("channelId")
        if not account_id:
            raise DeliveryError("YouTube video response did not identify its destination channel")
        title = item.get("snippet", {}).get("channelTitle", "")
        return Identity(str(account_id), str(title))

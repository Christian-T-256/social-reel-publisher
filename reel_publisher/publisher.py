from collections.abc import Callable, Iterable

from .base import Platform
from .guardrails import PinStore, verify_after, verify_before
from .models import Media, PublishResult


class Publisher:
    def __init__(self, pins: PinStore, log: Callable[[str], None] = print):
        self.pins = pins
        self.log = log

    def verify(self, platform: Platform) -> None:
        pin = self.pins.get(platform.name)
        actual = platform.resolve_destination()
        verify_before(platform.name, pin, actual)
        self.log(
            f"[{platform.name}] VERIFIED destination {actual.display_name} [{actual.account_id}]"
        )

    def publish_one(self, platform: Platform, media: Media) -> PublishResult:
        pin = self.pins.get(platform.name)
        before = platform.resolve_destination()
        verify_before(platform.name, pin, before)
        self.log(
            f"[{platform.name}] PRECHECK matched {before.display_name} [{before.account_id}]"
        )

        submission = platform.start_publish(media, self.log)
        self.log(
            f"[{platform.name}] ACCEPTED {submission.artifact_id} state={submission.accepted_state}; "
            "not claiming success yet"
        )
        receipt = platform.wait_for_terminal(submission, self.log)
        after = platform.resolve_landed_destination(receipt)
        verify_after(platform.name, pin, after, receipt.artifact_id)
        self.log(
            f"[{platform.name}] POSTCHECK matched {after.display_name} [{after.account_id}]"
        )
        self.log(
            f"[{platform.name}] OK {receipt.artifact_id} terminal={receipt.terminal_state}"
        )
        return PublishResult(
            platform=platform.name,
            artifact_id=receipt.artifact_id,
            terminal_state=receipt.terminal_state,
            destination=after,
            public_url=receipt.public_url,
        )

    def publish_all(self, platforms: Iterable[Platform], media: Media) -> list[PublishResult]:
        selected = list(platforms)
        self.log("[batch] verifying every destination before the first upload")
        for platform in selected:
            self.verify(platform)
        return [self.publish_one(platform, media) for platform in selected]

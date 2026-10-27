from pathlib import Path

import pytest

from reel_publisher.demo import DemoPins, MockPlatform, _identities, happy_platforms, run_demo
from reel_publisher.errors import (
    DeliveryError,
    DestinationMismatchError,
    MissingPinError,
    PostPublishMismatchError,
)
from reel_publisher.guardrails import PinStore
from reel_publisher.models import Identity, Media
from reel_publisher.publisher import Publisher


MEDIA = Media(
    "Demo",
    "Fictional caption",
    "fixtures/demo-reel.mp4",
    "https://media.example.com/demo-reel.mp4",
)


def test_happy_demo_polls_every_platform_to_terminal_state():
    lines = []
    platforms = happy_platforms()
    results = Publisher(DemoPins(), lines.append).publish_all(platforms, MEDIA)

    assert [result.terminal_state for result in results] == [
        "succeeded",
        "FINISHED",
        "SEND_TO_USER_INBOX",
    ]
    assert all(platform.started for platform in platforms)
    assert any("not claiming success yet" in line for line in lines)


def test_wrong_account_is_refused_before_upload():
    wrong = MockPlatform(
        "youtube",
        Identity("yt-jamie-personal-demo", "Jamie Rivera"),
        ("succeeded",),
        "must-not-exist",
    )

    with pytest.raises(DestinationMismatchError, match="REFUSED before upload"):
        Publisher(DemoPins()).publish_one(wrong, MEDIA)

    assert wrong.started is False


def test_batch_preflight_finishes_before_any_upload():
    good = happy_platforms()[0]
    wrong = MockPlatform(
        "instagram",
        Identity("ig-other-demo", "other_demo"),
        ("FINISHED",),
        "must-not-exist",
    )

    with pytest.raises(DestinationMismatchError):
        Publisher(DemoPins()).publish_all([good, wrong], MEDIA)

    assert good.started is False
    assert wrong.started is False


def test_post_publish_destination_is_checked_independently():
    expected = _identities()["instagram"]
    platform = MockPlatform(
        "instagram",
        expected,
        ("FINISHED",),
        "reel-demo-002",
        landed_identity=Identity("ig-other-demo", "other_demo"),
    )

    with pytest.raises(PostPublishMismatchError, match="ALERT after creation"):
        Publisher(DemoPins()).publish_one(platform, MEDIA)


def test_missing_pin_fails_closed(tmp_path: Path):
    platform = happy_platforms()[0]

    with pytest.raises(MissingPinError, match="no destination is pinned"):
        Publisher(PinStore(tmp_path / "pins.json")).publish_one(platform, MEDIA)

    assert platform.started is False


class AcceptedButFailed(MockPlatform):
    def wait_for_terminal(self, submission, log):
        log("[youtube] POLL state=failed")
        raise DeliveryError("processing failed")


def test_http_acceptance_is_not_delivery_success():
    platform = AcceptedButFailed(
        "youtube", _identities()["youtube"], ("failed",), "video-demo-failed"
    )

    with pytest.raises(DeliveryError, match="processing failed"):
        Publisher(DemoPins()).publish_one(platform, MEDIA)


def test_full_dry_run_includes_refusal_proof():
    lines = []
    assert run_demo("all", lines.append) is True
    assert any("mocked happy path" in line for line in lines)
    assert any("REFUSED before upload" in line for line in lines)
    assert any("PASS no upload call was made" in line for line in lines)

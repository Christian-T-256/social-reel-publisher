from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .base import Log, Platform
from .errors import DestinationMismatchError
from .models import Identity, Media, Pin, Receipt, Submission
from .publisher import Publisher


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mock_responses.json"


def _fixture() -> dict:
    with FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _identities() -> dict[str, Identity]:
    return {
        name: Identity(value["account_id"], value["display_name"])
        for name, value in _fixture()["identities"].items()
    }


class DemoPins:
    def get(self, platform: str) -> Pin:
        identity = _identities()[platform]
        return Pin(identity.account_id, identity.display_name)


@dataclass
class MockPlatform(Platform):
    name: str
    identity: Identity
    states: tuple[str, ...]
    artifact_id: str
    landed_identity: Identity | None = None
    started: bool = False

    def resolve_destination(self) -> Identity:
        return self.identity

    def start_publish(self, media: Media, log: Log) -> Submission:
        self.started = True
        log(f"[{self.name}] MOCK HTTP 200 returned an id")
        return Submission(self.artifact_id, "ACCEPTED")

    def wait_for_terminal(self, submission: Submission, log: Log) -> Receipt:
        for state in self.states:
            log(f"[{self.name}] POLL state={state}")
        return Receipt(submission.artifact_id, self.states[-1], f"mock://{submission.artifact_id}")

    def resolve_landed_destination(self, receipt: Receipt) -> Identity:
        return self.landed_identity or self.identity


def happy_platforms() -> list[MockPlatform]:
    fixture = _fixture()
    identities = _identities()
    return [
        MockPlatform(
            "youtube",
            identities["youtube"],
            tuple(fixture["responses"]["youtube"]["states"]),
            fixture["responses"]["youtube"]["artifact_id"],
        ),
        MockPlatform(
            "instagram",
            identities["instagram"],
            tuple(fixture["responses"]["instagram"]["states"]),
            fixture["responses"]["instagram"]["artifact_id"],
        ),
        MockPlatform(
            "tiktok",
            identities["tiktok"],
            tuple(fixture["responses"]["tiktok"]["states"]),
            fixture["responses"]["tiktok"]["artifact_id"],
        ),
    ]


def run_demo(scenario: str = "all", log: Log = print) -> bool:
    media = Media(
        title="Three ways to make check-in easier",
        caption="A fictional short-form video for Northwind Dental. #Demo",
        local_file="fixtures/demo-reel.mp4",
        public_url="https://media.example.com/demo-reel.mp4",
    )
    publisher = Publisher(DemoPins(), log)

    if scenario in {"all", "happy"}:
        log("DRY RUN: mocked happy path")
        publisher.publish_all(happy_platforms(), media)

    if scenario in {"all", "wrong-account"}:
        log("DRY RUN: mocked wrong-account refusal")
        wrong = MockPlatform(
            "youtube",
            Identity(**_fixture()["wrong_identity"]),
            ("processing", "succeeded"),
            "must-not-exist",
        )
        try:
            publisher.publish_one(wrong, media)
        except DestinationMismatchError as exc:
            log(str(exc))
            if wrong.started:
                raise AssertionError("guardrail failure: upload started after a pin mismatch")
            log("[youtube] PASS no upload call was made")
        else:
            raise AssertionError("guardrail failure: wrong account was accepted")
    return True

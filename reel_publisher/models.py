from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Identity:
    account_id: str
    display_name: str


@dataclass(frozen=True)
class Pin:
    account_id: str
    display_name: str


@dataclass(frozen=True)
class Media:
    title: str
    caption: str
    local_file: str | None = None
    public_url: str | None = None


@dataclass
class Submission:
    artifact_id: str
    accepted_state: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Receipt:
    artifact_id: str
    terminal_state: str
    public_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishResult:
    platform: str
    artifact_id: str
    terminal_state: str
    destination: Identity
    public_url: str | None = None

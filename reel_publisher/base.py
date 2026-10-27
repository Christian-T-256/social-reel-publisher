from abc import ABC, abstractmethod
from collections.abc import Callable

from .models import Identity, Media, Receipt, Submission

Log = Callable[[str], None]


class Platform(ABC):
    name: str

    @abstractmethod
    def resolve_destination(self) -> Identity:
        """Resolve the account selected by the current credential."""

    @abstractmethod
    def start_publish(self, media: Media, log: Log) -> Submission:
        """Create or upload a resource, but do not treat acceptance as delivery."""

    @abstractmethod
    def wait_for_terminal(self, submission: Submission, log: Log) -> Receipt:
        """Poll until a documented successful terminal state or raise."""

    @abstractmethod
    def resolve_landed_destination(self, receipt: Receipt) -> Identity:
        """Resolve the destination again from the created resource or credential."""

from pathlib import Path

from .errors import DestinationMismatchError, MissingPinError, PostPublishMismatchError
from .io_utils import load_json, save_private_json
from .models import Identity, Pin


class PinStore:
    """Pins live outside source control and change only through an explicit command."""

    def __init__(self, path: Path):
        self.path = path

    def _data(self) -> dict:
        if not self.path.exists():
            return {"pins": {}}
        data = load_json(self.path)
        if not isinstance(data.get("pins"), dict):
            raise MissingPinError(f"pin registry is invalid: {self.path}")
        return data

    def get(self, platform: str) -> Pin:
        raw = self._data()["pins"].get(platform)
        if not isinstance(raw, dict) or not raw.get("account_id"):
            raise MissingPinError(
                f"{platform}: no destination is pinned; run --pin {platform} after verifying the account"
            )
        return Pin(str(raw["account_id"]), str(raw.get("display_name", "")))

    def set(self, platform: str, identity: Identity) -> None:
        data = self._data()
        data["pins"][platform] = {
            "account_id": identity.account_id,
            "display_name": identity.display_name,
        }
        save_private_json(self.path, data)


def verify_before(platform: str, pin: Pin, actual: Identity) -> None:
    if actual.account_id != pin.account_id:
        raise DestinationMismatchError(
            f"{platform}: REFUSED before upload. Token resolves to "
            f"{actual.display_name} [{actual.account_id}], but the pin is "
            f"{pin.display_name} [{pin.account_id}]"
        )


def verify_after(platform: str, pin: Pin, actual: Identity, artifact_id: str) -> None:
    if actual.account_id != pin.account_id:
        raise PostPublishMismatchError(
            f"{platform}: ALERT after creation of {artifact_id}. API reports destination "
            f"{actual.display_name} [{actual.account_id}], but the pin is "
            f"{pin.display_name} [{pin.account_id}]"
        )

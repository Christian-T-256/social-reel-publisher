import json
import stat

from reel_publisher.guardrails import PinStore
from reel_publisher.models import Identity


def test_pin_store_writes_private_separate_registry(tmp_path):
    path = tmp_path / "destination_pins.json"
    store = PinStore(path)
    identity = Identity("yt-northwind-demo", "Northwind Dental")

    store.set("youtube", identity)

    assert store.get("youtube").account_id == identity.account_id
    assert json.loads(path.read_text())["pins"]["youtube"]["display_name"] == "Northwind Dental"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

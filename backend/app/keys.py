"""Mapování tlačítek aplikace na Android keycodes (Android TV Remote protocol v2)."""
from androidtvremote2.remotemessage_pb2 import RemoteKeyCode

KEYS: dict[str, str] = {
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "ok": "KEYCODE_DPAD_CENTER",
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "guide": "KEYCODE_GUIDE",
    "vol_up": "KEYCODE_VOLUME_UP",
    "vol_down": "KEYCODE_VOLUME_DOWN",
    "mute": "KEYCODE_VOLUME_MUTE",
    "play_pause": "KEYCODE_MEDIA_PLAY_PAUSE",
    "play": "KEYCODE_MEDIA_PLAY",
    "pause": "KEYCODE_MEDIA_PAUSE",
    "stop": "KEYCODE_MEDIA_STOP",
    "rewind": "KEYCODE_MEDIA_REWIND",
    "forward": "KEYCODE_MEDIA_FAST_FORWARD",
    "power": "KEYCODE_POWER",
    "menu": "KEYCODE_MENU",
    "settings": "KEYCODE_SETTINGS",
    "input": "KEYCODE_TV_INPUT",
    "ch_up": "KEYCODE_CHANNEL_UP",
    "ch_down": "KEYCODE_CHANNEL_DOWN",
}

_VALID = set(RemoteKeyCode.keys())


def resolve(key: str) -> str:
    """Vrátí název keycodu; přijímá alias (např. "ok") i přímý název (KEYCODE_...)."""
    if key in KEYS:
        return KEYS[key]
    name = key if key.startswith("KEYCODE_") else f"KEYCODE_{key.upper()}"
    if name in _VALID:
        return name
    raise ValueError(f"neznámá klávesa: {key}")

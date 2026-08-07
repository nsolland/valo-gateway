from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROFILE_DIR = Path(__file__).with_name("profiles")


def list_style_profiles() -> list[str]:
    return sorted(path.stem for path in _PROFILE_DIR.glob("*_style.json"))


def load_style_profile(profile_id: str) -> dict[str, Any]:
    normalized = profile_id.strip().lower().replace("_", "-")
    for path in _PROFILE_DIR.glob("*_style.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("id") == normalized or path.stem.replace("_", "-") == normalized:
            return data
    raise KeyError(f"unknown style profile: {profile_id}")


def prompt_prefix(profile_id: str) -> str:
    profile = load_style_profile(profile_id)
    value = profile.get("default_prompt_prefix")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"style profile {profile_id!r} has no default_prompt_prefix")
    return value.strip()

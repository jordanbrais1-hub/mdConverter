"""Persistent user settings stored as JSON in the per-user app data folder."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .utils import app_data_dir, default_destination

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"


@dataclass
class AppSettings:
    # Output
    destination: str = ""
    lock_destination: bool = False          # remember the destination between sessions
    create_timestamped_subfolder: bool = True
    overwrite_existing: bool = False

    # Appearance: "System", "Light" or "Dark"
    appearance_mode: str = "System"

    # Optional online features. All are off by default so conversions stay local.
    llm_enabled: bool = False
    llm_base_url: str = ""                  # blank = official OpenAI endpoint
    llm_api_key: str = ""                   # blank = fall back to OPENAI_API_KEY
    llm_model: str = "gpt-4o-mini"
    llm_prompt: str = ""                    # blank = MarkItDown's default caption prompt
    allow_online_audio: bool = False        # MarkItDown transcribes audio via Google's web API

    @property
    def destination_path(self) -> Path:
        return Path(self.destination) if self.destination else default_destination()

    @property
    def effective_api_key(self) -> str:
        return self.llm_api_key or os.environ.get("OPENAI_API_KEY", "")

    @property
    def uses_network(self) -> bool:
        return self.llm_enabled or self.allow_online_audio

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        path = path or app_data_dir() / SETTINGS_FILE
        settings = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings (%s); using defaults.", exc)
            return settings

        # Ignore unknown keys and wrongly-typed values so an old or hand-edited
        # settings file can never stop the app from starting.
        for f in fields(cls):
            if f.name in data and isinstance(data[f.name], type(getattr(settings, f.name))):
                setattr(settings, f.name, data[f.name])
        if not settings.lock_destination:
            settings.destination = ""
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or app_data_dir() / SETTINGS_FILE
        data = asdict(self)
        if not self.lock_destination:
            data["destination"] = ""
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            log.error("Could not save settings: %s", exc)

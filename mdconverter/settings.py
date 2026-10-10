"""Persistent user settings stored as JSON in the per-user app data folder.

The LLM API key is the one secret the app handles. It is kept in the OS
credential vault (see secret_store) and is never written to settings.json.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlsplit

from . import secret_store
from .utils import app_data_dir, default_destination

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"
SECRET_FIELDS = {"llm_api_key"}            # never serialised to disk
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_llm_endpoint(url: str) -> str | None:
    """Return an error message if ``url`` is not a safe API endpoint, else None.

    Blank means the official OpenAI endpoint. Otherwise HTTPS is required, so the
    API key and documents are never sent in clear text. Plain HTTP is allowed
    only for servers on this computer (e.g. Ollama, LM Studio).
    """
    url = url.strip()
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return "The API endpoint is not a valid URL."
    if parts.scheme not in ("https", "http") or not parts.hostname:
        return "The API endpoint must start with https:// and include a host name."
    if parts.username or parts.password:
        return "Do not put credentials in the endpoint URL; use the API key field."
    if parts.scheme == "http" and parts.hostname.lower() not in LOCAL_HOSTS:
        return "Use https:// for remote servers. Plain http:// is only allowed for localhost."
    return None


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
    # Loaded from the OS credential vault, never from/to JSON. repr=False keeps it out of logs.
    llm_api_key: str = field(default="", repr=False)
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
            data = {}
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings (%s); using defaults.", exc)
            data = {}

        if not isinstance(data, dict):
            log.warning("Settings file has an unexpected format; using defaults.")
            data = {}

        # Ignore unknown keys and wrongly-typed values so an old or hand-edited
        # settings file can never stop the app from starting.
        for f in fields(cls):
            if f.name in SECRET_FIELDS:
                continue
            if f.name in data and isinstance(data[f.name], type(getattr(settings, f.name))):
                setattr(settings, f.name, data[f.name])
        if not settings.lock_destination:
            settings.destination = ""
        if validate_llm_endpoint(settings.llm_base_url):
            settings.llm_base_url = ""

        # Migrate a plain-text key written by version 1.0.x into the credential vault.
        legacy_key = data.get("llm_api_key")
        if isinstance(legacy_key, str) and legacy_key:
            secret_store.set_api_key(legacy_key)
            settings.save(path)
            log.info("Moved the API key from settings.json to the system credential store.")

        settings.llm_api_key = secret_store.get_api_key()
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or app_data_dir() / SETTINGS_FILE
        data = {k: v for k, v in asdict(self).items() if k not in SECRET_FIELDS}
        if not self.lock_destination:
            data["destination"] = ""
        try:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            log.error("Could not save settings: %s", exc)

    def set_api_key(self, value: str) -> bool:
        """Update the API key in memory and in the credential vault."""
        self.llm_api_key = value.strip()
        return secret_store.set_api_key(self.llm_api_key)

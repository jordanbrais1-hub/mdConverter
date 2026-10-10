import pytest

from mdconverter import secret_store


@pytest.fixture(autouse=True)
def fake_credential_store(monkeypatch):
    """Keep tests away from the real OS credential vault."""
    vault: dict[str, str] = {}
    monkeypatch.setattr(secret_store, "get_api_key", lambda: vault.get("key", ""))

    def set_key(value: str) -> bool:
        if value:
            vault["key"] = value
        else:
            vault.pop("key", None)
        return True

    monkeypatch.setattr(secret_store, "set_api_key", set_key)
    return vault

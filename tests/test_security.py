"""Regression tests for the security hardening controls."""

import json
from pathlib import Path

import pytest

from mdconverter.converter import ConfigurationError, build_markitdown, convert_file, Status
from mdconverter.settings import AppSettings, validate_llm_endpoint
from mdconverter.utils import (
    PathEscapeError,
    SourceItem,
    UnsafePathError,
    _validated_target,
    ensure_within,
    plan_output_paths,
)


# Obviously fake placeholder values, not real credentials.
FAKE_KEY = "sk-test-not-a-real-key-0000"  # gitleaks:allow
FAKE_LEGACY_KEY = "sk-legacy-not-a-real-key-0000"  # gitleaks:allow


# --- Secrets at rest ------------------------------------------------------- #
def test_api_key_is_never_written_to_settings_file(tmp_path, fake_credential_store):
    path = tmp_path / "settings.json"
    settings = AppSettings(llm_enabled=True)
    settings.set_api_key(FAKE_KEY)
    settings.save(path)

    assert FAKE_KEY not in path.read_text(encoding="utf-8")
    assert fake_credential_store["key"] == FAKE_KEY
    assert AppSettings.load(path).llm_api_key == FAKE_KEY


def test_legacy_plaintext_key_is_migrated_and_scrubbed(tmp_path, fake_credential_store):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_api_key": FAKE_LEGACY_KEY, "llm_model": "m"}), encoding="utf-8")

    loaded = AppSettings.load(path)

    assert loaded.llm_api_key == FAKE_LEGACY_KEY
    assert fake_credential_store["key"] == FAKE_LEGACY_KEY
    assert FAKE_LEGACY_KEY not in path.read_text(encoding="utf-8")


def test_api_key_hidden_from_repr():
    settings = AppSettings()
    settings.llm_api_key = "sk-should-not-appear"
    assert "sk-should-not-appear" not in repr(settings)


# --- Endpoint validation --------------------------------------------------- #
@pytest.mark.parametrize("url", ["", "https://api.openai.com/v1", "http://localhost:11434/v1", "http://127.0.0.1:1234/v1"])
def test_safe_endpoints_accepted(url):
    assert validate_llm_endpoint(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",          # API key would travel in clear text
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pass@example.com",  # credentials in URL end up in logs
        "https://",
    ],
)
def test_unsafe_endpoints_rejected(url):
    assert validate_llm_endpoint(url)


def test_unsafe_endpoint_blocks_converter(monkeypatch):
    settings = AppSettings(llm_enabled=True, llm_base_url="http://evil.example.com")
    settings.llm_api_key = "sk-x"
    with pytest.raises(ConfigurationError):
        build_markitdown(settings)


def test_unsafe_endpoint_in_settings_file_is_dropped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_base_url": "http://evil.example.com"}), encoding="utf-8")
    assert AppSettings.load(path).llm_base_url == ""


# --- Path handling --------------------------------------------------------- #
def test_ensure_within_blocks_traversal(tmp_path):
    ensure_within(tmp_path / "a" / "b.md", tmp_path)
    with pytest.raises(PathEscapeError):
        ensure_within(tmp_path / ".." / "evil.md", tmp_path)


def test_planned_outputs_stay_inside_output_dir(tmp_path):
    base = tmp_path / "in"
    (base / "deep" / "er").mkdir(parents=True)
    src = base / "deep" / "er" / "x.pdf"
    src.write_bytes(b"x")
    out = tmp_path / "out"
    plan = plan_output_paths([SourceItem(src, base)], out, overwrite=False)
    for target in plan.values():
        assert out.resolve() in target.resolve().parents


@pytest.mark.parametrize("name", ["evil.exe", "evil.bat", "evil.lnk", "evil.ps1", "evil.html"])
def test_open_refuses_non_markdown_files(tmp_path, name):
    target = tmp_path / name
    target.write_text("x", encoding="utf-8")
    with pytest.raises(UnsafePathError):
        _validated_target(target)


def test_open_allows_markdown_and_folders(tmp_path):
    md = tmp_path / "ok.md"
    md.write_text("# ok", encoding="utf-8")
    assert _validated_target(md) == md.resolve()
    assert _validated_target(tmp_path) == tmp_path.resolve()


# --- Network isolation ----------------------------------------------------- #
def test_conversion_never_fetches_urls(tmp_path):
    """A file whose name looks like a URL must be read as a local file."""

    class Recorder:
        def convert_local(self, path):
            self.called_with = path
            raise RuntimeError("stop")

        def convert(self, *_a, **_k):  # would accept URLs; must not be used
            raise AssertionError("convert() must not be used; it can fetch URLs")

    src = tmp_path / "https_example.com.html"
    src.write_text("<p>x</p>", encoding="utf-8")
    md = Recorder()
    result = convert_file(md, SourceItem(src), tmp_path / "x.md", AppSettings())
    assert result.status is Status.FAILED
    assert Path(md.called_with) == src


def test_audio_converter_removed_offline():
    from markitdown.converters import AudioConverter

    md = build_markitdown(AppSettings())
    assert not any(isinstance(r.converter, AudioConverter) for r in md._converters)

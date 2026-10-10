import sys

import pytest
from markitdown import FailedConversionAttempt, FileConversionException, UnsupportedFormatException

from mdconverter.converter import (
    BatchFinished,
    ConfigurationError,
    ConversionWorker,
    FileFinished,
    Status,
    build_markitdown,
    convert_file,
)
from mdconverter.settings import AppSettings
from mdconverter.utils import REPORT_FILENAME, SourceItem, discover_files, plan_output_paths


@pytest.fixture(scope="module")
def md():
    return build_markitdown(AppSettings())


def test_html_converts_to_markdown(md, tmp_path):
    src = tmp_path / "page.html"
    src.write_text("<h1>Title</h1><p>Hello <b>world</b></p>", encoding="utf-8")
    out = tmp_path / "out" / "page.md"

    result = convert_file(md, SourceItem(src), out, AppSettings())

    assert result.status is Status.SUCCESS
    text = out.read_text(encoding="utf-8")
    assert "# Title" in text and "**world**" in text


def test_csv_becomes_table(md, tmp_path):
    src = tmp_path / "data.csv"
    src.write_text("name,qty\napple,3\n", encoding="utf-8")
    result = convert_file(md, SourceItem(src), tmp_path / "data.md", AppSettings())
    assert result.status is Status.SUCCESS
    assert "| name | qty |" in (tmp_path / "data.md").read_text(encoding="utf-8")


def test_audio_skipped_when_offline(md, tmp_path):
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"\x00" * 16)
    result = convert_file(md, SourceItem(src), tmp_path / "talk.md", AppSettings())
    assert result.status is Status.SKIPPED
    assert not (tmp_path / "talk.md").exists()


class _RaisingConverter:
    def __init__(self, exc):
        self.exc = exc

    def convert_local(self, _path):
        raise self.exc


@pytest.mark.parametrize(
    "exc, expected",
    [
        (UnsupportedFormatException("nope"), Status.SKIPPED),
        (FileConversionException("bad file"), Status.FAILED),
        (RuntimeError("parser crashed"), Status.FAILED),
    ],
)
def test_conversion_errors_are_reported_not_raised(tmp_path, exc, expected):
    src = tmp_path / "broken.pdf"
    src.write_bytes(b"%PDF-garbage")
    out = tmp_path / "broken.md"

    result = convert_file(_RaisingConverter(exc), SourceItem(src), out, AppSettings())

    assert result.status is expected
    assert result.message
    assert not out.exists()


def test_failure_message_names_the_underlying_parser_error(tmp_path):
    class PdfConverter:
        pass

    try:
        raise ValueError("Unexpected EOF")
    except ValueError:
        attempt = FailedConversionAttempt(PdfConverter(), sys.exc_info())
    src = tmp_path / "broken.pdf"
    src.write_bytes(b"%PDF")

    exc = FileConversionException(attempts=[attempt])
    result = convert_file(_RaisingConverter(exc), SourceItem(src), tmp_path / "x.md", AppSettings())

    assert result.message == "Pdf parser error — ValueError: Unexpected EOF"


def test_llm_without_key_is_a_configuration_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        build_markitdown(AppSettings(llm_enabled=True))


def test_worker_runs_batch_and_writes_report(tmp_path):
    root = tmp_path / "in"
    (root / "sub").mkdir(parents=True)
    (root / "a.html").write_text("<p>A</p>", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("B", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    plan = plan_output_paths(discover_files([root]), out, overwrite=False)

    worker = ConversionWorker(list(plan.items()), out, AppSettings())
    worker.start()
    worker.join(timeout=120)

    events = []
    while not worker.events.empty():
        events.append(worker.events.get())
    finished = [e for e in events if isinstance(e, FileFinished)]
    final = events[-1]

    assert len(finished) == 2
    assert isinstance(final, BatchFinished) and not final.error
    assert all(r.status is Status.SUCCESS for r in final.results)
    assert (out / "in" / "sub" / "b.md").exists()
    assert (out / REPORT_FILENAME).exists()


def test_cancelled_worker_marks_remaining_files(tmp_path):
    items = []
    for i in range(3):
        p = tmp_path / f"f{i}.txt"
        p.write_text(str(i), encoding="utf-8")
        items.append((SourceItem(p), tmp_path / f"f{i}.md"))

    worker = ConversionWorker(items, tmp_path, AppSettings())
    worker.cancel()  # cancel before starting: nothing should be converted
    worker.run()  # run synchronously on this thread

    results = None
    while not worker.events.empty():
        e = worker.events.get()
        if isinstance(e, BatchFinished):
            results = e.results
    assert results is not None
    assert [r.status for r in results] == [Status.CANCELLED] * 3

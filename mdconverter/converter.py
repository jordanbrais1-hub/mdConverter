"""Conversion engine: wraps MarkItDown and runs batches on a background thread.

The GUI never calls MarkItDown directly. It starts a :class:`ConversionWorker`
and polls the worker's event queue from the Tk main loop, which keeps the
interface responsive and avoids touching Tk widgets from another thread.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Union

from .settings import AppSettings
from .utils import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, REPORT_FILENAME, SourceItem

log = logging.getLogger(__name__)


class Status(str, Enum):
    PENDING = "Pending"
    CONVERTING = "Converting"
    SUCCESS = "Done"
    WARNING = "Empty"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    CANCELLED = "Cancelled"


@dataclass
class ConversionResult:
    item: SourceItem
    status: Status
    output_path: Path | None = None
    message: str = ""
    duration: float = 0.0
    char_count: int = 0


# --------------------------------------------------------------------------- #
# MarkItDown setup
# --------------------------------------------------------------------------- #
class ConfigurationError(Exception):
    """Raised when the user's settings cannot produce a working converter."""


def build_markitdown(settings: AppSettings):
    """Create a MarkItDown instance that only uses the network when configured to.

    * Plugins are disabled, so third-party code is never loaded implicitly.
    * An LLM client is attached only when the user enabled it in Settings.
    * The audio converter (which uploads audio to Google's speech API) is
      removed unless online audio transcription was explicitly allowed. This
      also covers audio files found inside .zip archives.
    """
    # Imported lazily: MarkItDown pulls in heavy optional dependencies and
    # importing it here keeps application start-up fast.
    from markitdown import MarkItDown

    kwargs: dict = {"enable_plugins": False}

    if settings.llm_enabled:
        api_key = settings.effective_api_key
        if not api_key:
            raise ConfigurationError(
                "An LLM model is enabled in Settings but no API key is set."
            )
        if not settings.llm_model.strip():
            raise ConfigurationError("An LLM model is enabled in Settings but no model name is set.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ConfigurationError("The 'openai' package is required for LLM features.") from exc

        kwargs["llm_client"] = OpenAI(api_key=api_key, base_url=settings.llm_base_url.strip() or None)
        kwargs["llm_model"] = settings.llm_model.strip()
        if settings.llm_prompt.strip():
            kwargs["llm_prompt"] = settings.llm_prompt.strip()

    md = MarkItDown(**kwargs)

    if not settings.allow_online_audio:
        _remove_audio_converter(md)
    return md


def _remove_audio_converter(md) -> None:
    try:
        from markitdown.converters import AudioConverter
    except ImportError:
        return
    registry = getattr(md, "_converters", None)
    if isinstance(registry, list):
        registry[:] = [r for r in registry if not isinstance(getattr(r, "converter", None), AudioConverter)]
    else:  # MarkItDown internals changed; top-level audio files are still skipped below.
        log.warning("Could not disable MarkItDown's online audio converter.")


# --------------------------------------------------------------------------- #
# Single-file conversion
# --------------------------------------------------------------------------- #
def convert_file(md, item: SourceItem, output_path: Path, settings: AppSettings) -> ConversionResult:
    """Convert one file and write the Markdown. Never raises for per-file errors."""
    from markitdown import (
        FileConversionException,
        MissingDependencyException,
        UnsupportedFormatException,
    )

    suffix = item.path.suffix.lower()
    if suffix in AUDIO_EXTENSIONS and not settings.allow_online_audio:
        return ConversionResult(
            item,
            Status.SKIPPED,
            message="Audio transcription uses an online service. Enable it in Settings to convert audio.",
        )

    start = time.perf_counter()
    try:
        result = md.convert(item.path)
        text = (getattr(result, "markdown", None) or result.text_content or "").strip()
    except UnsupportedFormatException:
        return ConversionResult(item, Status.SKIPPED, message=f"Unsupported file format ({suffix or 'no extension'}).")
    except MissingDependencyException as exc:
        return ConversionResult(item, Status.FAILED, message=f"Missing optional dependency: {_first_line(exc)}")
    except FileConversionException as exc:
        return ConversionResult(item, Status.FAILED, message=_describe_conversion_failure(exc))
    except Exception as exc:  # noqa: BLE001 - any parser can fail on a corrupt file
        log.exception("Unexpected error converting %s", item.path)
        return ConversionResult(item, Status.FAILED, message=f"{type(exc).__name__}: {_first_line(exc)}")

    duration = time.perf_counter() - start

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        return ConversionResult(item, Status.FAILED, message=f"Could not write output: {exc}", duration=duration)

    if not text:
        hint = (
            "Images contain no extractable text unless an LLM vision model is configured in Settings."
            if suffix in IMAGE_EXTENSIONS and not settings.llm_enabled
            else "The converter produced no text (the file may be scanned, empty or image-only)."
        )
        return ConversionResult(item, Status.WARNING, output_path, hint, duration, 0)

    return ConversionResult(item, Status.SUCCESS, output_path, "", duration, len(text))


def _describe_conversion_failure(exc) -> str:
    """Turn MarkItDown's multi-line FileConversionException into one useful line."""
    for attempt in getattr(exc, "attempts", None) or []:
        info = getattr(attempt, "exc_info", None)
        if info and info[1] is not None:
            converter = type(attempt.converter).__name__.replace("Converter", "")
            return f"{converter} parser error — {type(info[1]).__name__}: {_first_line(info[1])}"
    return _first_line(exc)


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text.splitlines()[0][:300]


# --------------------------------------------------------------------------- #
# Batch worker
# --------------------------------------------------------------------------- #
@dataclass
class BatchStarted:
    total: int
    output_dir: Path


@dataclass
class FileStarted:
    index: int
    item: SourceItem


@dataclass
class FileFinished:
    index: int
    result: ConversionResult


@dataclass
class BatchFinished:
    results: list[ConversionResult]
    output_dir: Path
    report_path: Path | None
    cancelled: bool
    error: str = ""                      # set when the batch could not start at all
    elapsed: float = 0.0


WorkerEvent = Union[BatchStarted, FileStarted, FileFinished, BatchFinished]


class ConversionWorker(threading.Thread):
    """Converts a planned batch on a daemon thread, reporting through ``events``."""

    def __init__(self, jobs: list[tuple[SourceItem, Path]], output_dir: Path, settings: AppSettings) -> None:
        super().__init__(name="ConversionWorker", daemon=True)
        self.jobs = jobs
        self.output_dir = output_dir
        self.settings = settings
        self.events: queue.Queue[WorkerEvent] = queue.Queue()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        start = time.perf_counter()
        self.events.put(BatchStarted(len(self.jobs), self.output_dir))
        results: list[ConversionResult] = []

        try:
            md = build_markitdown(self.settings)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not fatal
            log.exception("Could not initialise MarkItDown")
            self.events.put(BatchFinished([], self.output_dir, None, False, error=str(exc)))
            return

        for index, (item, output_path) in enumerate(self.jobs):
            if self.cancelled:
                result = ConversionResult(item, Status.CANCELLED, message="Cancelled by user.")
            else:
                self.events.put(FileStarted(index, item))
                result = convert_file(md, item, output_path, self.settings)
                log.info("%s: %s %s", result.status.value, item.path, result.message)
            results.append(result)
            self.events.put(FileFinished(index, result))

        elapsed = time.perf_counter() - start
        report = write_report(results, self.output_dir, elapsed)
        self.events.put(BatchFinished(results, self.output_dir, report, self.cancelled, elapsed=elapsed))


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def summarize(results: list[ConversionResult]) -> dict[Status, int]:
    counts = {status: 0 for status in Status}
    for r in results:
        counts[r.status] += 1
    return counts


def format_report(results: list[ConversionResult], output_dir: Path, elapsed: float) -> str:
    """Render a human-readable Markdown report of a batch."""
    counts = summarize(results)
    lines = [
        "# Conversion Report",
        "",
        f"- **Date:** {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- **Output folder:** `{output_dir}`",
        f"- **Total files:** {len(results)}",
        f"- **Converted:** {counts[Status.SUCCESS]}",
        f"- **Converted with no text:** {counts[Status.WARNING]}",
        f"- **Failed:** {counts[Status.FAILED]}",
        f"- **Skipped:** {counts[Status.SKIPPED]}",
        f"- **Cancelled:** {counts[Status.CANCELLED]}",
        f"- **Time taken:** {elapsed:.1f} s",
        "",
    ]

    problems = [r for r in results if r.status not in (Status.SUCCESS,)]
    if problems:
        lines += ["## Files needing attention", "", "| Status | File | Details |", "|---|---|---|"]
        for r in problems:
            details = r.message.replace("|", "\\|")
            lines.append(f"| {r.status.value} | `{r.item.display_name}` | {details} |")
        lines.append("")

    done = [r for r in results if r.status is Status.SUCCESS]
    if done:
        lines += ["## Converted files", "", "| Source | Output | Characters | Time |", "|---|---|---|---|"]
        for r in done:
            rel = r.output_path.relative_to(output_dir) if r.output_path else ""
            lines.append(f"| `{r.item.display_name}` | `{rel}` | {r.char_count:,} | {r.duration:.2f} s |")
        lines.append("")

    return "\n".join(lines)


def write_report(results: list[ConversionResult], output_dir: Path, elapsed: float) -> Path | None:
    if not results:
        return None
    path = output_dir / REPORT_FILENAME
    try:
        path.write_text(format_report(results, output_dir, elapsed), encoding="utf-8")
    except OSError as exc:
        log.error("Could not write conversion report: %s", exc)
        return None
    return path

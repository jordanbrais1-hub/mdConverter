"""Filesystem helpers: file discovery, output path planning and OS integration.

Nothing in this module touches the GUI, so it can be unit-tested headlessly.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

from . import __app_name__

log = logging.getLogger(__name__)

# Extensions MarkItDown can convert. Used to filter files when a whole folder is
# imported, so we do not try to "convert" executables, fonts, etc. Files the
# user adds explicitly are always queued; the converter reports them if unsupported.
DOCUMENT_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".epub", ".msg", ".ipynb",
}
WEB_AND_TEXT_EXTENSIONS = {
    ".html", ".htm", ".xml", ".rss", ".atom", ".csv", ".json", ".jsonl",
    ".txt", ".text", ".md", ".markdown",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4"}
ARCHIVE_EXTENSIONS = {".zip"}

SUPPORTED_EXTENSIONS = (
    DOCUMENT_EXTENSIONS
    | WEB_AND_TEXT_EXTENSIONS
    | IMAGE_EXTENSIONS
    | AUDIO_EXTENSIONS
    | ARCHIVE_EXTENSIONS
)

OUTPUT_FOLDER_PREFIX = "Converted_Markdown_"
REPORT_FILENAME = "Conversion_Report.md"


@dataclass(frozen=True)
class SourceItem:
    """A file queued for conversion.

    ``base`` is the folder the user imported, if the file was found by scanning
    a folder. It is used to replicate the original sub-folder hierarchy in the
    output directory. Files added individually have ``base=None``.
    """

    path: Path
    base: Path | None = None

    @property
    def relative_output_stem(self) -> Path:
        """Relative path (without extension) the Markdown file should get."""
        if self.base is None:
            return Path(self.path.stem)
        # Keep the imported folder's own name as the top level, e.g.
        # dropping "Reports/" yields "<output>/Reports/2024/q1.md".
        top = self.base.name or self.base.drive.rstrip(":\\/") or "root"
        rel = self.path.relative_to(self.base)
        return Path(top) / rel.parent / rel.stem

    @property
    def display_name(self) -> str:
        """Short label for the UI and report, e.g. ``Reports/2024/q1.pdf``."""
        if self.base is None:
            return self.path.name
        return str(self.relative_output_stem.parent / self.path.name)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".") or path.name.startswith("~$")


def iter_folder(folder: Path) -> Iterable[Path]:
    """Yield supported files under ``folder`` recursively, in a stable order."""
    for root, dirs, files in os.walk(folder):
        # Prune hidden directories in place so os.walk does not descend into them.
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            path = Path(root) / name
            if not _is_hidden(path) and is_supported(path):
                yield path


def discover_files(paths: Iterable[str | Path]) -> list[SourceItem]:
    """Expand a mix of file and folder paths into a de-duplicated list of items."""
    items: list[SourceItem] = []
    seen: set[Path] = set()

    def add(item: SourceItem) -> None:
        key = item.path.resolve()
        if key not in seen:
            seen.add(key)
            items.append(item)

    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            base = path.resolve()
            for file in iter_folder(base):
                add(SourceItem(file, base))
        elif path.is_file():
            add(SourceItem(path.resolve()))
        else:
            log.warning("Skipping path that does not exist: %s", path)
    return items


# --------------------------------------------------------------------------- #
# Output planning
# --------------------------------------------------------------------------- #
def timestamped_folder_name(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{OUTPUT_FOLDER_PREFIX}{now:%Y-%m-%d_%H-%M-%S}"


def prepare_output_dir(destination: Path, create_timestamped_subfolder: bool) -> Path:
    """Create (if needed) and return the directory this batch writes into."""
    out = destination / timestamped_folder_name() if create_timestamped_subfolder else destination
    out.mkdir(parents=True, exist_ok=True)
    return out


def _with_counter(path: Path, n: int) -> Path:
    return path.with_name(f"{path.stem} ({n}){path.suffix}")


def plan_output_paths(
    items: Iterable[SourceItem], output_dir: Path, overwrite: bool
) -> dict[SourceItem, Path]:
    """Decide the output .md path for every item before conversion starts.

    Two inputs can map to the same name (``report.pdf`` and ``report.docx``),
    so later ones get a ``(1)``, ``(2)`` suffix. When ``overwrite`` is False,
    files that already exist on disk are also avoided.
    """
    planned: dict[SourceItem, Path] = {}
    taken: set[str] = set()
    for item in items:
        stem = item.relative_output_stem
        # Append rather than use .with_suffix(), which would clobber dots in "v1.2".
        candidate = output_dir / stem.parent / f"{stem.name}.md"
        n = 0
        target = candidate
        while str(target).lower() in taken or (not overwrite and target.exists()):
            n += 1
            target = _with_counter(candidate, n)
        taken.add(str(target).lower())
        planned[item] = target
    return planned


# --------------------------------------------------------------------------- #
# OS integration
# --------------------------------------------------------------------------- #
def open_path(path: Path) -> None:
    """Open a file or folder with the operating system's default handler."""
    path = Path(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def reveal_in_file_manager(path: Path) -> None:
    """Open the containing folder and, where supported, select the file."""
    path = Path(path)
    if sys.platform.startswith("win") and path.is_file():
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin" and path.is_file():
        subprocess.Popen(["open", "-R", str(path)])
    else:
        open_path(path if path.is_dir() else path.parent)


def app_data_dir() -> Path:
    """Per-user directory for settings and logs (created on first use)."""
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = root / __app_name__
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_destination() -> Path:
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


def resource_path(relative: str) -> Path:
    """Locate bundled resources both from source and inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def setup_logging() -> Path:
    """Log to a rotating file in the app data dir (and stderr when available)."""
    log_file = app_data_dir() / "mdconverter.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    ]
    # A windowed PyInstaller build has no console, so sys.stderr may be None.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_file


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # unreachable, keeps type checkers happy

"""Entry point for mdConverter.

Run from source with ``python main.py``; this is also the script PyInstaller
bundles into ``mdConverter.exe``.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import traceback


def _ensure_std_streams() -> None:
    # In a windowed (no console) PyInstaller build sys.stdout/stderr are None,
    # and any library that prints a warning would crash. Send them to devnull.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _set_windows_app_id() -> None:
    # Groups the window under its own taskbar icon instead of python.exe's.
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mdConverter.App")
        except (AttributeError, OSError):
            pass


def main() -> int:
    multiprocessing.freeze_support()
    _ensure_std_streams()

    from mdconverter.utils import setup_logging

    log_file = setup_logging()
    log = logging.getLogger("mdconverter")
    _set_windows_app_id()

    try:
        from mdconverter.gui import App

        app = App()
    except Exception:
        log.exception("Failed to start the user interface")
        _show_fatal_error(traceback.format_exc(), log_file)
        return 1

    def report_callback_exception(exc_type, exc, tb) -> None:
        # Errors inside Tk callbacks: log them and tell the user, but keep running.
        log.error("Unhandled UI error", exc_info=(exc_type, exc, tb))
        from tkinter import messagebox

        messagebox.showerror(
            "mdConverter",
            f"Something went wrong:\n\n{exc}\n\nDetails were written to:\n{log_file}",
        )

    app.report_callback_exception = report_callback_exception
    app.mainloop()
    return 0


def _show_fatal_error(details: str, log_file) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "mdConverter",
            f"mdConverter could not start.\n\nDetails were written to:\n{log_file}\n\n{details[-1500:]}",
        )
        root.destroy()
    except Exception:  # noqa: BLE001 - last resort, nothing else to do
        print(details, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

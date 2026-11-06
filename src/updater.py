import os
import sys
import threading
import json
import tempfile
import zipfile
import subprocess
import urllib.request
from urllib.parse import urlparse

import customtkinter as ctk

from . import config

FONT = "Arial"


def _parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)


def _fetch_remote_info(url: str, timeout: int = 6) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _resolve_download_url(download_url: str, timeout: int = 10) -> str:
    download_url = download_url.strip() if isinstance(download_url, str) else ""
    if download_url and urlparse(download_url).path.lower().endswith(".zip"):
        return download_url

    repository = urlparse(config.GITHUB_LINK)
    owner, _, name = repository.path.strip("/").partition("/")
    if repository.netloc.lower() != "github.com" or not owner or not name:
        return ""

    api_url = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PizzaTools-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            release = json.loads(resp.read().decode("utf-8"))
        assets = release.get("assets", [])
        preferred = next(
            (asset for asset in assets if asset.get("name", "").lower() == "pizza_tools.zip"),
            None,
        )
        if preferred is None:
            preferred = next(
                (asset for asset in assets if asset.get("name", "").lower().endswith(".zip")),
                None,
            )
        return preferred.get("browser_download_url", "") if preferred else ""
    except Exception:
        return ""


def _download_file(url: str, dest_path: str, progress_cb=None):
    with urllib.request.urlopen(url, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done  = 0
        chunk = 1024 * 64

        with open(dest_path, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if progress_cb:
                    progress_cb(done, total)


def _get_app_root() -> str:
    here = os.path.abspath(sys.argv[0])
    if os.path.basename(os.path.dirname(here)).lower() == "src":
        return os.path.dirname(os.path.dirname(here))
    return os.path.dirname(here)


def _apply_update_and_restart(zip_path: str, app_root: str):
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable

    main_pyw = os.path.join(app_root, "main.pyw")
    bat_path = os.path.join(tempfile.gettempdir(), "pizza_tools_update.bat")
    pid      = os.getpid()

    bat_content = f"""@echo off
chcp 65001 >nul
title Pizza Tools Updater

echo Waiting for Pizza Tools to close...
:wait_loop
tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul 2>&1
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo Applying update...
powershell -NoProfile -Command ^
    "Expand-Archive -Path '{zip_path}' -DestinationPath '{app_root}' -Force"

if errorlevel 1 (
    echo [ERROR] Failed to extract update.
    pause
    goto cleanup
)

echo Restarting Pizza Tools...
start "" "{pythonw}" "{main_pyw}"

:cleanup
del "{zip_path}" >nul 2>&1
del "%~f0" >nul 2>&1
"""

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


class UpdateDialog(ctk.CTkToplevel):

    def __init__(self, parent, remote_version: str, changelog: str,
                 download_url: str, theme: dict, text_color: str):
        super().__init__(parent)

        self._parent       = parent
        self._download_url = download_url
        self._theme        = theme
        self._text_color   = text_color

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        t   = theme
        txt = text_color

        self.configure(fg_color=t["bg"])

        self._card = ctk.CTkFrame(self, corner_radius=16, fg_color=t["card"],
                                  border_width=1, border_color=t["accent"])
        self._card.pack(fill="both", expand=True, padx=1, pady=1)

        self._dx = self._dy = 0
        self._card.bind("<ButtonPress-1>", self._start_move)
        self._card.bind("<B1-Motion>",     self._do_move)

        header = ctk.CTkFrame(self._card, fg_color=t["btn"], corner_radius=12)
        header.pack(fill="x", padx=12, pady=(12, 0))
        header.bind("<ButtonPress-1>", self._start_move)
        header.bind("<B1-Motion>",     self._do_move)
        ctk.CTkLabel(header, text="🍕  Update Available!",
                     font=(FONT, 15, "bold"), text_color="#ffffff").pack(pady=10)

        info = ctk.CTkFrame(self._card, fg_color="transparent")
        info.pack(fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(info, text=f"Current version:  {config.APP_VERSION}",
                     font=(FONT, 12), text_color=txt, anchor="w").pack(fill="x")
        ctk.CTkLabel(info, text=f"New version:      {remote_version}",
                     font=(FONT, 12, "bold"), text_color=t["btn_hover"], anchor="w").pack(fill="x", pady=(2, 0))

        if changelog:
            ctk.CTkLabel(self._card, text="What's new:", font=(FONT, 11, "bold"),
                         text_color=txt, anchor="w").pack(fill="x", padx=20, pady=(12, 2))
            ctk.CTkLabel(self._card, text=changelog, font=(FONT, 11),
                         text_color=txt, anchor="w", justify="left",
                         wraplength=320).pack(fill="x", padx=20)

        self._progress_frame = ctk.CTkFrame(self._card, fg_color="transparent")
        self._progress_frame.pack(fill="x", padx=20, pady=(10, 0))

        self._status_lbl = ctk.CTkLabel(self._progress_frame, text="",
                                        font=(FONT, 11), text_color=txt)
        self._status_lbl.pack(fill="x")

        self._progress = ctk.CTkProgressBar(self._progress_frame, height=8)
        self._progress.set(0)

        btn_row = ctk.CTkFrame(self._card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=14)

        self._update_btn = ctk.CTkButton(
            btn_row, text="Update Now",
            font=(FONT, 12, "bold"),
            fg_color=t["btn"], hover_color=t["btn_hover"], text_color="#ffffff",
            corner_radius=8, height=36,
            command=self._start_download,
        )
        self._update_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._later_btn = ctk.CTkButton(
            btn_row, text="Later",
            font=(FONT, 12),
            fg_color="transparent", hover_color=t["accent"], text_color=txt,
            border_width=1, border_color=t["accent"],
            corner_radius=8, height=36,
            command=self.destroy,
        )
        self._later_btn.pack(side="left", fill="x", expand=True)

        self.update_idletasks()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        px = parent.winfo_x() + (parent.winfo_width()  // 2) - (w // 2)
        py = parent.winfo_y() + (parent.winfo_height() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")

    def _start_move(self, event):
        self._dx = event.x_root - self.winfo_x()
        self._dy = event.y_root - self.winfo_y()

    def _do_move(self, event):
        self.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _start_download(self):
        if not self._download_url:
            self._set_status("No download URL configured.", error=True)
            return

        self._update_btn.configure(state="disabled", text="Downloading...")
        self._later_btn.configure(state="disabled")
        self._progress.pack(fill="x", pady=(4, 0))
        self._set_status("Connecting to GitHub...")

        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        try:
            tmp_dir  = tempfile.mkdtemp(prefix="pizza_update_")
            zip_path = os.path.join(tmp_dir, "PizzaTools_update.zip")

            self._after_status("Downloading...")

            def on_progress(done, total):
                if total > 0:
                    mb_done  = done  / 1_048_576
                    mb_total = total / 1_048_576
                    self._after_status(f"{mb_done:.1f} / {mb_total:.1f} MB", progress=done / total)
                else:
                    self._after_status(f"{done / 1_048_576:.1f} MB downloaded...")

            _download_file(self._download_url, zip_path, progress_cb=on_progress)

            if not zipfile.is_zipfile(zip_path):
                raise ValueError("Downloaded file is not a valid ZIP.")

            self._after_status("Applying update & restarting...", progress=1.0)

            _apply_update_and_restart(zip_path, _get_app_root())

            self._parent.after(800, self._parent.exit_app)

        except Exception as e:
            self._after_status(f"Error: {e}", error=True)
            self.after(0, lambda: self._update_btn.configure(state="normal", text="Retry"))
            self.after(0, lambda: self._later_btn.configure(state="normal"))

    def _after_status(self, text: str, progress: float | None = None, error: bool = False):
        self.after(0, lambda: self._set_status(text, progress, error))

    def _set_status(self, text: str, progress: float | None = None, error: bool = False):
        try:
            self._status_lbl.configure(text=text, text_color="#ef4444" if error else self._text_color)
            if progress is not None:
                self._progress.set(progress)
        except Exception:
            pass


def check_for_update(app, theme: dict, text_color: str, silent: bool = True):
    def worker():
        info = _fetch_remote_info(config.GITHUB_VERSION_URL)
        if not info:
            if not silent:
                app.after(0, lambda: _show_offline(app, theme, text_color))
            return

        remote_version = info.get("version", "")
        changelog      = info.get("changelog", "")
        download_url   = info.get("download_url", "")

        if not remote_version:
            return

        if _parse_version(remote_version) > _parse_version(config.APP_VERSION):
            download_url = _resolve_download_url(download_url)
            app.after(0, lambda: _show_update_dialog(
                app, remote_version, changelog, download_url, theme, text_color))
        elif not silent:
            app.after(0, lambda: _show_up_to_date(app, theme, text_color))

    threading.Thread(target=worker, daemon=True).start()


def _show_update_dialog(app, remote_version, changelog, download_url, theme, text_color):
    try:
        UpdateDialog(app, remote_version, changelog, download_url, theme, text_color).focus()
    except Exception:
        pass


def _show_up_to_date(app, theme, text_color):
    try:
        t   = theme
        top = ctk.CTkToplevel(app)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(fg_color=t["bg"])

        card = ctk.CTkFrame(top, corner_radius=12, fg_color=t["card"],
                            border_width=1, border_color=t["accent"])
        card.pack(fill="both", expand=True, padx=1, pady=1)

        ctk.CTkLabel(card, text="✅  You're up to date!",
                     font=(FONT, 13, "bold"), text_color=text_color).pack(padx=24, pady=18)
        ctk.CTkLabel(card, text=f"v{config.APP_VERSION}",
                     font=(FONT, 11), text_color=text_color).pack(padx=24, pady=(0, 10))

        ctk.CTkButton(card, text="OK", font=(FONT, 12, "bold"),
                      fg_color=t["btn"], hover_color=t["btn_hover"],
                      text_color="#ffffff", corner_radius=8, height=34,
                      command=top.destroy).pack(padx=24, pady=(0, 14), fill="x")

        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        top.geometry(f"{w}x{h}+{app.winfo_x() + (app.winfo_width() // 2) - (w // 2)}"
                     f"+{app.winfo_y() + (app.winfo_height() // 2) - (h // 2)}")
        top.focus()
    except Exception:
        pass


def _show_offline(app, theme, text_color):
    try:
        t   = theme
        top = ctk.CTkToplevel(app)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(fg_color=t["bg"])

        card = ctk.CTkFrame(top, corner_radius=12, fg_color=t["card"],
                            border_width=1, border_color=t["accent"])
        card.pack(fill="both", expand=True, padx=1, pady=1)

        ctk.CTkLabel(card, text="⚠️  No Connection",
                     font=(FONT, 13, "bold"), text_color=text_color).pack(padx=24, pady=(18, 4))
        ctk.CTkLabel(card, text="Could not reach GitHub.",
                     font=(FONT, 11), text_color=text_color).pack(padx=24, pady=(0, 10))

        ctk.CTkButton(card, text="OK", font=(FONT, 12, "bold"),
                      fg_color=t["btn"], hover_color=t["btn_hover"],
                      text_color="#ffffff", corner_radius=8, height=34,
                      command=top.destroy).pack(padx=24, pady=(0, 14), fill="x")

        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        top.geometry(f"{w}x{h}+{app.winfo_x() + (app.winfo_width() // 2) - (w // 2)}"
                     f"+{app.winfo_y() + (app.winfo_height() // 2) - (h // 2)}")
        top.focus()
    except Exception:
        pass

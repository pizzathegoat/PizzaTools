import os
import sys
import threading
import json
import tempfile
import zipfile
import subprocess
import urllib.request
from urllib.error import URLError
from tkinter import messagebox

import customtkinter as ctk

from . import config

FONT = "Arial"


def _parse_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)


def _fetch_remote_info(url: str, timeout: int = 6) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "PizzaTools-Updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        info = json.load(response)
    if not isinstance(info, dict):
        raise ValueError("GitHub returned invalid update information.")
    return info


def _fetch_backup_release():
    repo = config.GITHUB_LINK.removeprefix("https://github.com/").rstrip("/")
    url = f"https://raw.githubusercontent.com/{repo}/main/version.json"
    info = _fetch_remote_info(url)
    version = info.get("version", "")
    download_url = info.get("download_url", "")
    if _parse_version(version) <= _parse_version(config.APP_VERSION):
        return None
    expected = f"{config.GITHUB_LINK.rstrip('/')}/releases/download/"
    if not isinstance(download_url, str) or not download_url.startswith(expected) or not download_url.lower().endswith("/pizza_tools.zip"):
        return None
    return {
        "tag_name": version,
        "body": info.get("changelog", ""),
        "assets": [{"name": "Pizza_Tools.zip", "browser_download_url": download_url}],
    }


def _stream_download(url, dest_path, progress_cb, accept):
    request = urllib.request.Request(
        url, headers={"User-Agent": "PizzaTools-Updater", "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
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


def _download_file(url, dest_path, progress_cb=None, *, api_url=None, retry_cb=None):
    try:
        _stream_download(url, dest_path, progress_cb, "*/*")
        if zipfile.is_zipfile(dest_path):
            return
        raise ValueError("The release download is not a valid ZIP.")
    except (URLError, TimeoutError, ValueError):
        if not api_url:
            raise
    if retry_cb is not None:
        retry_cb()
    _stream_download(api_url, dest_path, progress_cb, "application/octet-stream")
    if not zipfile.is_zipfile(dest_path):
        raise ValueError("The GitHub API did not return a valid ZIP.")


def _get_app_root() -> str:
    here = os.path.abspath(sys.argv[0])
    if os.path.basename(os.path.dirname(here)).lower() == "src":
        return os.path.dirname(os.path.dirname(here))
    return os.path.dirname(here)


def _apply_update_and_restart(zip_path: str, app_root: str):
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable
    helper_path = os.path.join(os.path.dirname(zip_path), "install_update.py")
    log_path = os.path.join(config.CONFIG_DIR, "update.log")
    helper = r'''
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import zipfile

archive, destination, parent_pid, pythonw = sys.argv[1:]
root = Path(destination).resolve()
try:
    print("Waiting for Pizza Tools to close...", flush=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, int(parent_pid))
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 60000) != 0:
                raise RuntimeError("Pizza Tools did not exit within 60 seconds.")
        finally:
            kernel.CloseHandle(handle)
    elif ctypes.get_last_error() != 87:
        raise ctypes.WinError(ctypes.get_last_error())
    stage = Path(archive).parent / "staged"
    stage.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            target = (stage / entry.filename).resolve()
            if not target.is_relative_to(stage.resolve()):
                raise ValueError("Invalid archive path.")
        package.extractall(stage)
    payloads = [
        launcher.parent
        for launcher in stage.rglob("main.pyw")
        if (launcher.parent / "src" / "config.py").is_file()
    ]
    if stage in payloads:
        payload = stage
    else:
        outer_payloads = [
            folder for folder in payloads
            if not any(other in folder.parents for other in payloads)
        ]
        if len(outer_payloads) != 1:
            raise ValueError("The ZIP does not contain one valid Pizza Tools installation.")
        payload = outer_payloads[0]
    nested_payloads = {
        folder for folder in payloads if payload in folder.parents
    }
    backup = Path(archive).parent / "backup"
    changed = []
    try:
        for source in payload.rglob("*"):
            if not source.is_file() or nested_payloads.intersection(source.parents):
                continue
            relative = source.relative_to(payload)
            if {".git", ".idea", "__pycache__"}.intersection(relative.parts):
                continue
            target = root / relative
            saved = backup / relative
            existed = target.exists()
            if existed:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            target.parent.mkdir(parents=True, exist_ok=True)
            changed.append((target, saved, existed))
            shutil.copy2(source, target)
        subprocess.Popen([pythonw, str(root / "main.pyw")], cwd=str(root), close_fds=True)
    except Exception:
        for target, saved, existed in reversed(changed):
            if existed:
                shutil.copy2(saved, target)
            else:
                target.unlink(missing_ok=True)
        raise
    print("Update installed and restart launched.", flush=True)
except Exception:
    traceback.print_exc()
    sys.stderr.flush()
    ctypes.windll.user32.MessageBoxW(None, r"Update failed. Details are in %APPDATA%\PizzaTools\update.log", "Pizza Tools Update", 16)
    sys.exit(1)
'''
    with open(helper_path, "w", encoding="utf-8") as stream:
        stream.write(helper)
    with open(log_path, "w", encoding="utf-8") as log:
        subprocess.Popen(
            [pythonw, helper_path, zip_path, app_root, str(os.getpid()), pythonw],
            cwd=app_root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )


class UpdateDialog(ctk.CTkToplevel):

    def __init__(self, parent, remote_version: str, changelog: str,
                 download_url: str, theme: dict, text_color: str, *, asset_api_url=None):
        super().__init__(parent)

        self._parent       = parent
        self._download_url = download_url
        self._asset_api_url = asset_api_url
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
        ctk.CTkLabel(header, text="Update Available!",
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

            _download_file(
                self._download_url, zip_path, progress_cb=on_progress, api_url=self._asset_api_url,
                retry_cb=lambda: self._after_status("Trying the GitHub API...", progress=0),
            )

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
        try:
            info = _fetch_remote_info(config.GITHUB_RELEASE_API_URL)
        except (OSError, ValueError) as error:
            detail = str(error)
            try:
                info = _fetch_backup_release()
            except (OSError, ValueError):
                info = None
            if info is None:
                if not silent:
                    app.after(0, lambda: _show_offline(app, theme, text_color, detail))
                return

        remote_version = info.get("tag_name", "")
        changelog      = info.get("body") or ""
        asset = next(
            (asset for asset in info.get("assets", []) if asset.get("name", "").lower() == "pizza_tools.zip"),
            {},
        )
        download_url = asset.get("browser_download_url", "")
        asset_api_url = asset.get("url")

        if info.get("draft") or info.get("prerelease"):
            return

        if _parse_version(remote_version) == (0,):
            if not silent:
                app.after(0, lambda: messagebox.showerror("Update", "The latest release needs a numeric version tag, such as v1.0.2.", parent=app))
            return

        if _parse_version(remote_version) > _parse_version(config.APP_VERSION):
            if not download_url:
                if not silent:
                    app.after(0, lambda: messagebox.showerror("Update", "The latest release has no Pizza_Tools.zip attachment yet.", parent=app))
                return
            app.after(0, lambda: _show_update_dialog(
                app, remote_version, changelog, download_url, theme, text_color, asset_api_url=asset_api_url))
        elif not silent:
            app.after(0, lambda: _show_up_to_date(app, theme, text_color))

    threading.Thread(target=worker, daemon=True).start()


def _show_update_dialog(app, remote_version, changelog, download_url, theme, text_color, *, asset_api_url=None):
    try:
        UpdateDialog(
            app, remote_version, changelog, download_url, theme, text_color, asset_api_url=asset_api_url,
        ).focus()
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


def _show_offline(app, theme, text_color, detail):
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
        ctk.CTkLabel(card, text=f"Could not check the latest GitHub release.\n{detail}",
                     font=(FONT, 11), text_color=text_color, wraplength=290).pack(padx=24, pady=(0, 10))

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

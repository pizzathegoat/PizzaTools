import os
import re
import time
import shutil
import difflib
import subprocess
import winreg
import ctypes
from ctypes import wintypes

DEFAULT_STEAM_INSTALL_PATH = r"C:\Program Files (x86)\Steam"

TH32CS_SNAPPROCESS = 0x00000002


class _ProcessEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def find_steam_install_path():
    registry_lookups = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]

    for hive, key_path, value_name in registry_lookups:
        try:
            key = winreg.OpenKey(hive, key_path)
            value, _ = winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            if value:
                normalized = os.path.normpath(value)
                if os.path.isdir(normalized):
                    return normalized
        except Exception:
            continue

    if os.path.isdir(DEFAULT_STEAM_INSTALL_PATH):
        return DEFAULT_STEAM_INSTALL_PATH

    return None


from .onlinefix_utils import (
    get_steam_library_folders,
    get_installed_steam_games,
    clean_archive_name,
    find_matching_game,
    find_game_for_payload,
    resolve_payload_source_dir,
    resolve_target_game_dir,
    apply_game_fix,
    process_onlinefix_folder,
    process_onlinefix_archive,
)


def _enumerate_process_names():
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1):
        return

    entry = _ProcessEntry32()
    entry.dwSize = ctypes.sizeof(_ProcessEntry32)

    try:
        has_process = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while has_process:
            yield entry.szExeFile.decode(errors="ignore")
            has_process = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)


def is_steam_running():
    try:
        return any(name.lower() == "steam.exe" for name in _enumerate_process_names())
    except Exception:
        return False


def _wait_until_steam_closed(timeout):
    waited = 0.0
    interval = 0.5
    while is_steam_running() and waited < timeout:
        time.sleep(interval)
        waited += interval
    return not is_steam_running()


def close_steam(steam_exe_path, shutdown_timeout=10):
    try:
        if not is_steam_running():
            return "already_closed"

        subprocess.Popen([steam_exe_path, "-shutdown"])

        if _wait_until_steam_closed(shutdown_timeout):
            return "closed"
        return "timeout"
    except Exception:
        return "error"


def start_or_restart_steam(steam_exe_path, shutdown_timeout=10):
    try:
        if is_steam_running():
            subprocess.Popen([steam_exe_path, "-shutdown"])
            _wait_until_steam_closed(shutdown_timeout)

            subprocess.Popen([steam_exe_path])
            return "restarted"
        else:
            subprocess.Popen([steam_exe_path])
            return "started"
    except Exception:
        return "error"
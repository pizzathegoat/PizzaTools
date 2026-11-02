import os
import shutil
import zipfile
from . import steam_utils

def _ensure_depotcache(steam_path):
    if not steam_path:
        return None
    depotcache = os.path.join(steam_path, "depotcache")
    if not os.path.isdir(depotcache):
        try:
            os.makedirs(depotcache, exist_ok=True)
        except Exception:
            return None
    return depotcache

def install_manifest_file(source_path, steam_path=None, target_dir=None):
    if steam_path is None:
        steam_path = steam_utils.find_steam_install_path()
    if not steam_path:
        return False, "Steam installation path not found"
    depotcache = _ensure_depotcache(steam_path)
    if not depotcache:
        return False, f"Failed to create depotcache: {steam_path}\\depotcache"
    filename = os.path.basename(source_path)
    if not filename.lower().endswith(".manifest"):
        return False, f"Not a manifest file: {filename}"
    try:
        destination = os.path.join(depotcache, filename)
        shutil.copy2(source_path, destination)
        return True, destination
    except Exception as e:
        return False, f"Copy failed: {e}"

def install_manifests_from_zip(zip_path, steam_path=None, target_dir=None):
    if steam_path is None:
        steam_path = steam_utils.find_steam_install_path()
    if not steam_path:
        return 0, ["Steam installation path not found"]
    depotcache = _ensure_depotcache(steam_path)
    if not depotcache:
        return 0, [f"Failed to create depotcache: {steam_path}\\depotcache"]
    copied = 0
    errors = []
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if not info.filename.lower().endswith(".manifest"):
                    continue
                base = os.path.basename(info.filename)
                if not base:
                    continue
                try:
                    data = archive.read(info)
                    destination = os.path.join(depotcache, base)
                    with open(destination, "wb") as f:
                        f.write(data)
                    copied += 1
                except Exception as e:
                    errors.append(f"{base}: {e}")
    except zipfile.BadZipFile:
        return 0, ["Invalid ZIP file"]
    except Exception as e:
        return 0, [f"Read error: {e}"]
    return copied, errors

def is_manifest_only_zip(zip_path):
    PAYLOAD_EXT = (".dll", ".exe", ".ini", ".pak", ".bin", ".dat",
                   ".lua", ".bundle", ".assets", ".unity3d", ".uasset")
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            has_manifest = False
            for info in archive.infolist():
                if info.is_dir():
                    continue
                lower = info.filename.lower()
                if lower.endswith(".manifest"):
                    has_manifest = True
                    continue
                if lower.endswith(PAYLOAD_EXT):
                    return False
            return has_manifest
    except Exception:
        return False

def has_manifests(zip_path):
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if info.filename.lower().endswith(".manifest"):
                    return True
    except Exception:
        pass
    return False

def extract_manifests_only(zip_path):
    entries = []
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if not info.filename.lower().endswith(".manifest"):
                    continue
                base = os.path.basename(info.filename)
                if not base:
                    continue
                try:
                    entries.append((base, archive.read(info)))
                except Exception:
                    continue
    except Exception:
        return []
    return entries
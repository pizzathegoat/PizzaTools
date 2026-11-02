import json
import os
import threading
import time
import urllib.request

from . import config

CACHE_DIR = os.path.join(config.CONFIG_DIR, "covers")
RETRY_SECONDS = 6 * 60 * 60
_MEMORY = {}
_GUARD = threading.Lock()
_LOCKS = {}


def _app_lock(appid):
    with _GUARD:
        return _LOCKS.setdefault(str(appid), threading.Lock())


def _cache_path(appid):
    return os.path.join(CACHE_DIR, f"{appid}.json")


def _read_cache(appid):
    try:
        with open(_cache_path(appid), "r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _write_cache(appid, metadata):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(appid)
    temporary = f"{path}.{threading.get_ident()}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(metadata, stream)
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def save_app_metadata(appid, metadata):
    appid = str(appid)
    with _app_lock(appid):
        value = dict(metadata)
        with _GUARD:
            _MEMORY[appid] = value
        try:
            _write_cache(appid, value)
        except OSError:
            pass


def get_app_metadata(appid, timeout=2.5):
    appid = str(appid).strip()
    if not appid.isdigit():
        return {"name": f"App {appid}", "header_image": None}

    with _app_lock(appid):
        with _GUARD:
            cached = _MEMORY.get(appid)
        if cached is None:
            cached = _read_cache(appid)
        if cached:
            try:
                retry_after = float(cached.get("_retry_after", 0) or 0)
            except (TypeError, ValueError):
                retry_after = 0
            if cached.get("name") == f"App {appid}" and not cached.get("header_image") and not retry_after:
                cached["_retry_after"] = time.time() + RETRY_SECONDS
                try:
                    _write_cache(appid, cached)
                except OSError:
                    pass
                retry_after = cached["_retry_after"]
            if not retry_after or retry_after > time.time():
                with _GUARD:
                    _MEMORY[appid] = dict(cached)
                return dict(cached)

        stale = dict(cached) if cached else None
        request = urllib.request.Request(
            f"https://store.steampowered.com/api/appdetails?appids={appid}&l=en",
            headers={"User-Agent": "PizzaTools/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            result = payload.get(appid, {})
            details = result.get("data", {}) if result.get("success") else {}
            metadata = {
                "name": details.get("name") or f"App {appid}",
                "header_image": details.get("header_image"),
            }
            if metadata["name"] == f"App {appid}" and not metadata["header_image"]:
                metadata["_retry_after"] = time.time() + RETRY_SECONDS
        except Exception:
            metadata = stale or {"name": f"App {appid}", "header_image": None}
            metadata["_retry_after"] = time.time() + RETRY_SECONDS

        with _GUARD:
            _MEMORY[appid] = dict(metadata)
        try:
            _write_cache(appid, metadata)
        except OSError:
            pass
        return dict(metadata)


def get_cached_app_name(appid):
    appid = str(appid).strip()
    if not appid.isdigit():
        return None
    with _app_lock(appid):
        with _GUARD:
            cached = _MEMORY.get(appid)
        if cached is None:
            cached = _read_cache(appid)
            if cached:
                with _GUARD:
                    _MEMORY[appid] = dict(cached)
    if not cached:
        return None
    name = cached.get("name")
    return name if name else None


def get_app_name(appid, timeout=2.5):
    name = get_app_metadata(appid, timeout=timeout).get("name")
    return name if name and not name.startswith("App ") else None

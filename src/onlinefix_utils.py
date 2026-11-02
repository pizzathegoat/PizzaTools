import os
import re
import stat
import shutil
import difflib
import tempfile
import zipfile
import subprocess
import winreg
import ctypes
from . import config
NON_PAYLOAD_EXTENSIONS = {'.url', '.nfo', '.lnk', '.md', '.gitkeep', '.ds_store'}
NON_PAYLOAD_FILENAMES = {'desktop.ini', 'thumbs.db', '.ds_store'}
def _ensure_writable(path):
    try:
        if os.path.exists(path):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            if hasattr(ctypes, "windll"):
                FILE_ATTRIBUTE_NORMAL = 0x80
                ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_NORMAL)
    except Exception:
        pass
def _is_payload_file(filename):
    f_lower = filename.lower()
    if f_lower in NON_PAYLOAD_FILENAMES:
        return False
    _, ext = os.path.splitext(f_lower)
    if ext in NON_PAYLOAD_EXTENSIONS:
        return False
    if ext == '.txt':
        if f_lower in {'steam_appid.txt', 'interfaces.txt', 'dlc.txt', 'settings.txt', 'onlinefix.txt', 'appid.txt'}:
            return True
        if any(w in f_lower for w in ['readme', 'instruction', 'install', 'how_to', 'online-fix', 'changelog', 'help', 'info', 'note']):
            return False
    return True
def find_rar_extractor(custom_path=None):
    if custom_path and os.path.isfile(custom_path):
        return custom_path
    for name in ["unrar.exe", "unrar", "winrar.exe", "winrar", "7z.exe", "7z", "7za.exe", "7za"]:
        p = shutil.which(name)
        if p and os.path.isfile(p):
            return p
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe", ""),
        (winreg.HKEY_CURRENT_USER, r"Software\WinRAR", "exe64"),
        (winreg.HKEY_CURRENT_USER, r"Software\WinRAR", "exe32"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\7-Zip", "Path"),
        (winreg.HKEY_CURRENT_USER, r"Software\7-Zip", "Path"),
    ]
    for hive, key_path, val_name in reg_paths:
        try:
            k = winreg.OpenKey(hive, key_path)
            val, _ = winreg.QueryValueEx(k, val_name)
            winreg.CloseKey(k)
            if val:
                val = val.strip('"')
                if os.path.isdir(val):
                    for exe_name in ["7z.exe", "7za.exe", "WinRAR.exe", "UnRAR.exe"]:
                        z_path = os.path.join(val, exe_name)
                        if os.path.isfile(z_path):
                            return z_path
                elif os.path.isfile(val):
                    folder = os.path.dirname(val)
                    unrar_path = os.path.join(folder, "UnRAR.exe")
                    if os.path.isfile(unrar_path):
                        return unrar_path
                    return val
        except Exception:
            continue
    candidates = [
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files\WinRAR\WinRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\7-Zip\7za.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    tar_path = shutil.which("tar.exe") or shutil.which("tar")
    if tar_path and os.path.isfile(tar_path):
        return tar_path
    return None
def extract_rar_archive(rar_path, dest_dir, password="online-fix.me", custom_extractor=None):
    extractor = find_rar_extractor(custom_extractor)
    if not extractor:
        return False, "Kein WinRAR oder 7-Zip auf dem PC gefunden."
    ext_lower = extractor.lower()
    os.makedirs(dest_dir, exist_ok=True)
    dest_slash = os.path.normpath(dest_dir) + os.sep
    passwords_to_try = []
    if password:
        passwords_to_try.append(password)
        if password.lower() != password:
            passwords_to_try.append(password.lower())
    if "online-fix.me" not in passwords_to_try:
        passwords_to_try.append("online-fix.me")
    if "Online-Fix.me" not in passwords_to_try:
        passwords_to_try.append("Online-Fix.me")
    if "cs.rin.ru" not in passwords_to_try:
        passwords_to_try.append("cs.rin.ru")
    passwords_to_try.append("")
    def run_cmd(pwd):
        if "unrar.exe" in ext_lower or ("unrar" in ext_lower and "winrar" not in ext_lower):
            cmd = [extractor, "x", "-o+", "-inul", "-y"]
            if pwd:
                cmd.append(f"-p{pwd}")
            else:
                cmd.append("-p-")
            cmd.extend([rar_path, dest_slash])
        elif "winrar.exe" in ext_lower or "winrar" in ext_lower:
            cmd = [extractor, "x", "-ibck", "-inul", "-o+", "-y"]
            if pwd:
                cmd.append(f"-p{pwd}")
            else:
                cmd.append("-p-")
            cmd.extend([rar_path, dest_slash])
        elif "7z" in ext_lower:
            cmd = [extractor, "x", "-y", "-aoa"]
            if pwd:
                cmd.append(f"-p{pwd}")
            cmd.extend([f"-o{dest_dir}", rar_path])
        elif "tar" in ext_lower:
            cmd = [extractor, "-xf", rar_path, "-C", dest_dir]
        else:
            return -1, "Nicht unterstÃ¼tzter Entpacker."
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo,
            timeout=300
        )
        return res.returncode, None
    last_err = None
    for pwd in passwords_to_try:
        try:
            code, err = run_cmd(pwd)
            if code == 0:
                return True, None
            last_err = f"Exit-Code {code}"
        except Exception as e:
            last_err = str(e)
    return False, f"Entpacken fehlgeschlagen ({last_err})."
def get_steam_library_folders(steam_path):
    libraries = []
    if steam_path and os.path.isdir(steam_path):
        libraries.append(os.path.normpath(steam_path))
    if not steam_path:
        return libraries
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(vdf_path):
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            matches = re.findall(r'"path"\s*"([^"]+)"', content, re.IGNORECASE)
            for m in matches:
                norm = os.path.normpath(m.replace(r"\\", "\\"))
                if os.path.isdir(norm) and norm.lower() not in [l.lower() for l in libraries]:
                    libraries.append(norm)
        except Exception:
            pass
    return libraries
def get_installed_steam_games(steam_path):
    libraries = get_steam_library_folders(steam_path)
    games = {}
    for lib in libraries:
        steamapps = os.path.join(lib, "steamapps")
        common = os.path.join(steamapps, "common")
        if os.path.isdir(steamapps):
            try:
                for item in os.listdir(steamapps):
                    if item.lower().startswith("appmanifest_") and item.lower().endswith(".acf"):
                        acf_path = os.path.join(steamapps, item)
                        try:
                            with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                                acf_content = f.read()
                            name_match = re.search(r'"name"\s*"([^"]+)"', acf_content, re.IGNORECASE)
                            dir_match = re.search(r'"installdir"\s*"([^"]+)"', acf_content, re.IGNORECASE)
                            appid_match = re.search(r'"appid"\s*"([^"]+)"', acf_content, re.IGNORECASE)
                            display_name = name_match.group(1) if name_match else ""
                            installdir = dir_match.group(1) if dir_match else ""
                            appid = appid_match.group(1) if appid_match else ""
                            if installdir:
                                full_game_path = os.path.join(common, installdir)
                                if os.path.isdir(full_game_path):
                                    game_entry = {
                                        "display_name": display_name or installdir,
                                        "folder_name": installdir,
                                        "path": full_game_path,
                                        "appid": appid,
                                        "library": lib
                                    }
                                    games[installdir.lower()] = game_entry
                                    if display_name:
                                        games[display_name.lower()] = game_entry
                        except Exception:
                            pass
            except Exception:
                pass
        if os.path.isdir(common):
            try:
                for folder in os.listdir(common):
                    folder_path = os.path.join(common, folder)
                    if os.path.isdir(folder_path):
                        if folder.lower() not in games:
                            games[folder.lower()] = {
                                "display_name": folder,
                                "folder_name": folder,
                                "path": folder_path,
                                "appid": "",
                                "library": lib
                            }
            except Exception:
                pass
    return games
def clean_archive_name(filename):
    base = os.path.basename(filename)
    base = re.sub(r'\.(rar|zip|7z|tar|gz|tgz)$', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\s*\(\d+\)$', '', base)
    patterns = [
        r'\[Online[-_]?Fix(?:\.me)?\]',
        r'\(Online[-_]?Fix(?:\.me)?\)',
        r'\[OFME\]',
        r'Fix[._\s\-]?Repair[._\s\-]?Steam(?:[._\s\-]?[vV]\d+)?[._\s\-]?(?:Generic)?',
        r'Fix[._\s\-]?Repair(?:[._\s\-]?[vV]\d+)?',
        r'Fix[._\s\-]?Online(?:[._\s\-]?[vV]\d+)?',
        r'-OnlineFix(?:\.me)?',
        r'_OnlineFix(?:\.me)?',
        r'Online-Fix\.me',
        r'Online-Fix',
        r'OnlineFix',
        r'Steam Generic',
        r'Steam_Generic',
        r'Steam-Rip',
        r'Steam_Rip',
        r'SteamRip',
        r'Multiplayer[._\s\-]?Fix',
        r'LAN[._\s\-]?Fix',
        r'Crack[._\s\-]?Only',
        r'\bSteamFix\b',
        r'\bSteam_Fix\b',
        r'\bSteam Fix\b',
        r'\bFix\b',
        r'\bRepair\b',
        r'\bGeneric\b',
        r'\bPatch\b',
        r'\bHotfix\b',
        r'\bRepack\b',
        r'\bFitGirl\b',
        r'\bDODI\b',
        r'\bElAmigos\b',
        r'v\d+([._]\d+)*[a-z]?',
        r'\b[vV]\d+\b',
        r'Build[._\s\-]?\d+',
        r'\bEarly[._\s\-]?Access\b',
        r'\bDemo\b',
    ]
    cleaned = base
    for p in patterns:
        cleaned = re.sub(p, ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[_\.\-\+]', ' ', cleaned)
    cleaned = re.sub(r'[\[\]\(\)\{\}]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned
def _normalize_string(s):
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', str(s).lower())
def _tokenize(s):
    cleaned = clean_archive_name(s)
    words = re.findall(r'[a-z0-9]+', cleaned.lower())
    noise = {'fix', 'repair', 'online', 'generic', 'steam', 'crack', 'v', 'build', 'the', 'a', 'an', 'only'}
    return [w for w in words if w not in noise]
def find_matching_game(query, installed_games):
    if not query or not installed_games:
        return None, 0.0
    raw_query = os.path.basename(os.path.normpath(query))
    cleaned_query = clean_archive_name(raw_query)
    norm_query = _normalize_string(cleaned_query)
    norm_raw = _normalize_string(raw_query)
    if not norm_query and not norm_raw:
        return None, 0.0
    for key, game in installed_games.items():
        candidates = [
            _normalize_string(key),
            _normalize_string(game.get("folder_name", "")),
            _normalize_string(game.get("display_name", ""))
        ]
        if game.get("appid"):
            candidates.append(str(game.get("appid")).strip())
        for c in candidates:
            if not c:
                continue
            if norm_query == c or norm_raw == c:
                return game, 1.0
    query_tokens = set(_tokenize(raw_query))
    best_game = None
    best_score = 0.0
    for key, game in installed_games.items():
        disp_tokens = set(_tokenize(game.get("display_name", "")))
        folder_tokens = set(_tokenize(game.get("folder_name", "")))
        game_tokens = disp_tokens | folder_tokens
        if game_tokens and query_tokens:
            common = game_tokens & query_tokens
            if game_tokens.issubset(query_tokens) and len(game_tokens) >= 1:
                score = 0.90 + (len(common) / max(len(query_tokens), len(game_tokens))) * 0.09
                if score > best_score:
                    best_score = score
                    best_game = game
            elif query_tokens.issubset(game_tokens) and len(query_tokens) >= 1:
                score = 0.85 + (len(common) / len(game_tokens)) * 0.10
                if score > best_score:
                    best_score = score
                    best_game = game
        candidates = [
            _normalize_string(key),
            _normalize_string(game.get("folder_name", "")),
            _normalize_string(game.get("display_name", ""))
        ]
        for c in candidates:
            if not c:
                continue
            if len(norm_query) >= 3 and len(c) >= 3:
                if norm_query in c or c in norm_query:
                    ratio = min(len(norm_query), len(c)) / max(len(norm_query), len(c))
                    if ratio > best_score and ratio >= 0.5:
                        best_score = ratio
                        best_game = game
            ratio = difflib.SequenceMatcher(None, norm_query, c).ratio()
            if ratio > best_score and ratio >= 0.70:
                best_score = ratio
                best_game = game
    return best_game, best_score
def find_game_for_payload(source_root, query_name, games_cache):
    if not games_cache:
        return None, 0.0
    if query_name:
        match, score = find_matching_game(query_name, games_cache)
        if match and score >= 0.70:
            return match, score
    if source_root and os.path.isdir(source_root):
        try:
            for item in os.listdir(source_root):
                item_path = os.path.join(source_root, item)
                if os.path.isdir(item_path):
                    match, score = find_matching_game(item, games_cache)
                    if match and score >= 0.70:
                        return match, score
        except Exception:
            pass
    if source_root and os.path.isdir(source_root):
        try:
            for root, _dirs, files in os.walk(source_root):
                rel = os.path.relpath(root, source_root)
                if rel.count(os.sep) > 4:
                    continue
                for f in files:
                    f_lower = f.lower()
                    if f_lower == "steam_appid.txt":
                        try:
                            with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as af:
                                appid = af.read().strip()
                                for g in games_cache.values():
                                    if g.get("appid") and str(g.get("appid")).strip() == appid:
                                        return g, 1.0
                        except Exception:
                            pass
                    elif f_lower.endswith(".exe"):
                        exe_stem = os.path.splitext(f)[0]
                        if exe_stem.lower() not in {"unitycrashhandler64", "unitycrashhandler32", "crashreporter", "unins000", "setup"}:
                            match, score = find_matching_game(exe_stem, games_cache)
                            if match and score >= 0.70:
                                return match, score
        except Exception:
            pass
    return None, 0.0
def _is_wrapper_name(name, game_folder_name=None, game_display_name=None):
    norm_name = _normalize_string(name)
    if not norm_name:
        return True
    generic_wrappers = {
        'onlinefix', 'onlinefixme', 'fix', 'steamfix', 'crack', 'release', 'update',
        'patch', 'game', 'files', 'payload', 'steamgeneric', 'fixrepair', 'crackonly'
    }
    if norm_name in generic_wrappers:
        return True
    cleaned = _normalize_string(clean_archive_name(name))
    if cleaned in generic_wrappers or not cleaned:
        return True
    if game_folder_name:
        norm_game_folder = _normalize_string(game_folder_name)
        if norm_name == norm_game_folder or cleaned == norm_game_folder:
            return True
    if game_display_name:
        norm_display = _normalize_string(game_display_name)
        if norm_name == norm_display or cleaned == norm_display:
            return True
    return False
def resolve_payload_source_dir(extracted_root, target_game_path=None, target_game_folder_name=None, target_game_display_name=None):
    if not os.path.isdir(extracted_root):
        return extracted_root
    current = extracted_root
    while os.path.isdir(current):
        try:
            entries = os.listdir(current)
        except Exception:
            break
        dirs = [e for e in entries if os.path.isdir(os.path.join(current, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(current, e))]
        payload_files = [f for f in files if _is_payload_file(f)]
        if len(payload_files) > 0:
            break
        if len(dirs) != 1:
            break
        d = dirs[0]
        d_path = os.path.join(current, d)
        if target_game_path and os.path.isdir(target_game_path):
            target_sub = os.path.join(target_game_path, d)
            if os.path.isdir(target_sub):
                if not _is_wrapper_name(d, target_game_folder_name, target_game_display_name):
                    break
                try:
                    inner_entries = os.listdir(d_path)
                    match_found = False
                    for ie in inner_entries:
                        if os.path.exists(os.path.join(target_sub, ie)):
                            match_found = True
                            break
                    if match_found:
                        break
                except Exception:
                    pass
        current = d_path
    return current
def resolve_target_game_dir(target_game_dir):
    return os.path.normpath(target_game_dir) if target_game_dir else target_game_dir
def apply_game_fix(source_dir, target_game_dir):
    target_game_dir = resolve_target_game_dir(target_game_dir)
    copied_count = 0
    error_names = []
    for root, _dirs, files in os.walk(source_dir):
        rel_root = os.path.relpath(root, source_dir)
        dest_subdir = target_game_dir if rel_root == "." else os.path.join(target_game_dir, rel_root)
        for filename in files:
            if not _is_payload_file(filename) and filename.lower().endswith(('.url', '.lnk', '.gitkeep', '.ds_store')):
                continue
            if filename.lower() in NON_PAYLOAD_FILENAMES:
                continue
            src_path = os.path.join(root, filename)
            dest_path = os.path.join(dest_subdir, filename)
            rel_path = filename if rel_root == "." else os.path.join(rel_root, filename)
            try:
                os.makedirs(dest_subdir, exist_ok=True)
                if os.path.exists(dest_path):
                    _ensure_writable(dest_path)
                shutil.copy2(src_path, dest_path)
                copied_count += 1
            except Exception:
                try:
                    _ensure_writable(dest_path)
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    shutil.copy2(src_path, dest_path)
                    copied_count += 1
                except Exception:
                    error_names.append(rel_path)
    return copied_count, error_names
def process_onlinefix_folder(folder_path, steam_path, games_cache=None):
    folder_name = os.path.basename(os.path.normpath(folder_path))
    if games_cache is None:
        games_cache = get_installed_steam_games(steam_path)
    game_match, score = find_game_for_payload(folder_path, folder_name, games_cache)
    if not game_match:
        return {
            "status": "game_not_found",
            "game_name": folder_name,
            "copied_count": 0,
            "errors": [],
            "error_msg": None
        }
    game_title = game_match.get("display_name") or game_match.get("folder_name", "Game")
    game_dir = game_match["path"]
    payload_dir = resolve_payload_source_dir(
        folder_path,
        target_game_path=game_dir,
        target_game_folder_name=game_match.get("folder_name"),
        target_game_display_name=game_match.get("display_name")
    )
    copied_count, errors = apply_game_fix(payload_dir, game_dir)
    return {
        "status": "success",
        "game_name": game_title,
        "copied_count": copied_count,
        "errors": errors,
        "error_msg": None
    }
def process_onlinefix_archive(file_path, steam_path, password="online-fix.me", games_cache=None):
    filename = os.path.basename(file_path)
    lower_path = file_path.lower()
    temp_dir = tempfile.mkdtemp(prefix="pizza_fix_")
    try:
        success = False
        err = None
        if lower_path.endswith(('.rar', '.7z')):
            success, err = extract_rar_archive(file_path, temp_dir, password=password)
        elif lower_path.endswith('.zip'):
            try:
                archive_password = password.encode("utf-8") if password else None
                with zipfile.ZipFile(file_path, "r") as archive:
                    archive.extractall(temp_dir, pwd=archive_password)
                success = True
                err = None
            except Exception as zip_error:
                success, err = extract_rar_archive(file_path, temp_dir, password=password)
                if not success and not err:
                    err = str(zip_error)
        elif lower_path.endswith(('.tar', '.gz', '.tgz', '.tar.gz')):
            try:
                import tarfile
                with tarfile.open(file_path, "r:*") as t:
                    t.extractall(temp_dir)
                success = True
                err = None
            except Exception as te:
                success = False
                err = str(te)
        if not success:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "status": "extract_error",
                "game_name": None,
                "copied_count": 0,
                "errors": [],
                "error_msg": f"{filename}: {err or 'Extraction failed'}"
            }
        if games_cache is None:
            games_cache = get_installed_steam_games(steam_path)
        game_match, score = find_game_for_payload(temp_dir, filename, games_cache)
        if not game_match:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "status": "game_not_found",
                "game_name": filename,
                "copied_count": 0,
                "errors": [],
                "error_msg": None
            }
        game_title = game_match.get("display_name") or game_match.get("folder_name", "Game")
        game_dir = game_match["path"]
        payload_dir = resolve_payload_source_dir(
            temp_dir,
            target_game_path=game_dir,
            target_game_folder_name=game_match.get("folder_name"),
            target_game_display_name=game_match.get("display_name")
        )
        copied_count, errors = apply_game_fix(payload_dir, game_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {
            "status": "success",
            "game_name": game_title,
            "copied_count": copied_count,
            "errors": errors,
            "error_msg": None
        }
    except Exception as ex:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {
            "status": "extract_error",
            "game_name": None,
            "copied_count": 0,
            "errors": [],
            "error_msg": str(ex)
        }
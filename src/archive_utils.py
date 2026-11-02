import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from .onlinefix_utils import find_rar_extractor, extract_rar_archive
from .file_utils import ensure_target_directory
from .steam_metadata import get_app_name

def _get_game_name_from_appid(app_id):
    return get_app_name(app_id)

def extract_lua_files_from_zip(zip_path, target_dir):
    extracted_count = 0
    error_names = []
    app_ids = []

    if not ensure_target_directory(target_dir):
        return 0, ["could not create target directory"], []

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if not info.filename.lower().endswith(".lua"):
                    continue
                filename = os.path.basename(info.filename)
                if not filename:
                    continue
                try:
                    data = archive.read(info)
                    destination = os.path.join(target_dir, filename)
                    with open(destination, "wb") as out_file:
                        out_file.write(data)
                    extracted_count += 1

                    base_name = os.path.splitext(filename)[0]
                    if base_name.isdigit():
                        app_ids.append(base_name)
                except Exception:
                    error_names.append(filename)
    except zipfile.BadZipFile:
        return 0, ["invalid zip file"], []
    except Exception:
        return 0, ["could not read zip file"], []
    game_names = []
    unique_app_ids = list(dict.fromkeys(app_ids))
    if unique_app_ids:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_app_ids))) as executor:
            game_names = [name for name in executor.map(_get_game_name_from_appid, unique_app_ids) if name]
    return extracted_count, error_names, game_names
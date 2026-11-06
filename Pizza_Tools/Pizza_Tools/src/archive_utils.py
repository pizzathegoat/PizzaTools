import os
import zipfile
from .onlinefix_utils import find_rar_extractor, extract_rar_archive


def extract_lua_files_from_zip(zip_path, target_dir):
    extracted_count = 0
    error_names = []
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
                except Exception:
                    error_names.append(filename)
    except zipfile.BadZipFile:
        return 0, ["invalid zip file"]
    except Exception:
        return 0, ["could not read zip file"]

    return extracted_count, error_names
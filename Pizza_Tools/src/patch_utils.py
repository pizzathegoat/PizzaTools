import os
import shutil


def copy_patch_files(patch_dir, dest_dir):
    copied_count = 0
    error_names = []

    for root, _dirs, files in os.walk(patch_dir):
        rel_root = os.path.relpath(root, patch_dir)
        dest_subdir = dest_dir if rel_root == "." else os.path.join(dest_dir, rel_root)

        for filename in files:
            src_path = os.path.join(root, filename)
            dest_path = os.path.join(dest_subdir, filename)
            rel_path = filename if rel_root == "." else os.path.join(rel_root, filename)

            try:
                os.makedirs(dest_subdir, exist_ok=True)
                shutil.copy2(src_path, dest_path)
                copied_count += 1
            except Exception:
                error_names.append(rel_path)

    return copied_count, error_names
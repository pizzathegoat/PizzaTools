import os

def ensure_target_directory(target_dir):
    try:
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
        return os.path.isdir(target_dir)
    except Exception:
        return False

import os

def find_lua_file_for_game(target_dir, game_id):
    exact_path = os.path.join(target_dir, f"{game_id}.lua")
    if os.path.isfile(exact_path):
        return exact_path

    try:
        for filename in os.listdir(target_dir):
            stem, ext = os.path.splitext(filename)
            if ext.lower() == ".lua" and stem.lower() == game_id.lower():
                return os.path.join(target_dir, filename)
    except Exception:
        pass

    return None

def remove_lua_file(file_path):
    try:
        os.remove(file_path)
        return True
    except Exception:
        return False
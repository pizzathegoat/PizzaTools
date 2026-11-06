import os
import sys
import json

def resource_path(*parts):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "PizzaTools")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

LOGO_FILENAME = resource_path("Pictures", "Logo.png")
APP_ICON = resource_path("Pictures", "app_icon.ico")
SETTINGS_ICON = resource_path("Pictures", "settings.png")
BACK_ICON = resource_path("Pictures", "back.png")
DISCORD_ICON = resource_path("Pictures", "discord.png")

PATCH_DIR = resource_path("Patch")

DISCORD_LINK = "https://discord.gg/aWGNxsf6Dd"
REG_APP_NAME = "PizzaTools"
DISCORD_RPC_CLIENT_ID = "1522551537661120593"

APP_VERSION         = "1.0.0"
GITHUB_LINK         = "https://github.com/pizzathegoat/PizzaTools"
GITHUB_VERSION_URL  = "https://raw.githubusercontent.com/pizzathegoat/PizzaTools/main/version.json"
GITHUB_RELEASES_URL = "https://github.com/pizzathegoat/PizzaTools/releases/latest"

THEMES = {
    "Dark": {"bg": "#121212", "card": "#1e1e1e", "accent": "#333333", "btn": "#2b2b2b", "btn_hover": "#3b3b3b"},
    "Blue": {"bg": "#0b1120", "card": "#172033", "accent": "#283b5e", "btn": "#1d4ed8", "btn_hover": "#2563eb"},
    "Green": {"bg": "#0f1712", "card": "#16221a", "accent": "#243d2c", "btn": "#15803d", "btn_hover": "#16a34a"},
    "Red": {"bg": "#1a0f0f", "card": "#241616", "accent": "#452222", "btn": "#b91c1c", "btn_hover": "#dc2626"}
}

TEXT_COLORS = {
    "White": "#ffffff",
    "Silver": "#b0b0b0",
    "Gold": "#fbbf24",
    "Cyan": "#22d3ee",
    "Crimson": "#f87171"
}

ONLINE_FIX_PASSWORD = "online-fix.me"

DEFAULT_SETTINGS = {
    "theme": "Dark",
    "text_color": "White",
    "target_dir": r"C:\Program Files (x86)\Steam\config\stplug-in",
    "discord_rpc": False,
    "delete_zip_after_extract": False,
    "delete_rar_after_patch": False,
    "steam_path": "",
    "glow_color": "auto",
    "custom_colors": {
        "bg": None,
        "card": None,
        "accent": None,
        "btn": None,
        "btn_hover": None
    }
}

GLOW_COLORS = {
    "Auto (Theme)": "auto",
    "Off": "off",
    "White": "#ffffff",
    "Blue": "#4f7cff",
    "Cyan": "#22d3ee",
    "Green": "#10b981",
    "Purple": "#8b5cf6",
    "Pink": "#ec4899",
    "Red": "#ef4444",
    "Gold": "#fbbf24",
}

MINI_LOGO_SIZE = (72, 72)
MINI_WINDOW_SIZE = 100
TRAY_ICON_SIZE = (128, 128)
TRANSPARENT_KEY = "#000001"


def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved_data = json.load(f)
                settings.update(saved_data)
        except Exception:
            pass
    return settings


def save_settings(settings):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception:
        pass


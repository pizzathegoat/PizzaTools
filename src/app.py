import os
import importlib.util
import json
import re
import shutil
import sys
import webbrowser
import threading
import ctypes
import tempfile
import zipfile
import urllib.request
import subprocess
import queue
import time

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageDraw, ImageTk, ImageOps

from . import config
from . import image_utils
from . import windows_integration
from . import archive_utils
from . import steam_utils
from . import steam_metadata
from . import onlinefix_utils
from . import patch_utils
from . import Game_remover
from . import manifest_utils
from . import file_utils
from .discord_rpc import DiscordRPC
from .theme_color_picker import ThemeColorPicker
from . import updater

FONT = "Arial"
SMALL_CORNER = 8

def _hex_to_rgb(hex_color):
    try:
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (255, 255, 255)


class LuaUploader(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PizzaTools.App.V2")
        except Exception:
            pass

        self.title("Pizza Tools by pizzathegoat , Daniel_99")

        try:
            scale = self.winfo_fpixels('1i') / 96
        except Exception:
            scale = 1.0

        base_w, base_h = 450, 700
        self.geometry(f"{int(base_w * scale)}x{int(base_h * scale)}")
        self.minsize(base_w, base_h)
        self.resizable(True, True)

        ctk.set_appearance_mode("dark")
        self.current_view = "uploader"
        self._game_metadata_queue = queue.Queue()
        self._game_metadata_pending = set()
        self._game_metadata_lock = threading.Lock()
        self._game_workers_started = False
        self._game_ctk_images = {}
        self._ui_icon_cache = {}
        self._games_render_after_id = None
        self._games_render_token = 0
        self._games_render_items = []
        self._games_render_index = 0
        self._games_render_signature = None
        self._games_all_items = []
        self._games_search_after_id = None
        self._current_game_filter_query = ""
        self._game_name_cache = {}
        self._onlinefix_process = None
        self._onlinefix_output_queue = queue.Queue()
        self._onlinefix_requirements_ready = False
        self._onlinefix_requirements_checking = False
        self._onlinefix_system_chrome = False
        self._onlinefix_downloader_path = config.resource_path("src", "onlinefix_downloader.py")

        self.reset_timer = None
        self.mini_reset_timer = None
        self.is_mini_mode = False
        self.tray_icon = None
        self._mini_size = config.MINI_LOGO_SIZE[0]
        self.discord = DiscordRPC(config.DISCORD_RPC_CLIENT_ID)

        self.load_config()
        self.load_images()
        self.init_ui()
        self.apply_theme(self.current_theme)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.settings.get("discord_rpc", False):
            threading.Thread(target=self.start_discord_rpc, daemon=True).start()


        self.after(4000, self._run_update_check)

        self.after(10000, self._poll_steam_status)

    def load_config(self):
        self.settings = config.load_settings()

        self.current_theme = self.settings.get("theme", "Dark")
        self.current_text_color = self.settings.get("text_color", "White")
        self.target_dir = self.settings.get("target_dir", r"C:\Program Files (x86)\Steam\config\Lua")

        if self.target_dir == r"C:\Program Files (x86)\Steam\config\Lua":
            self.target_dir = r"C:\Program Files (x86)\Steam\config\stplug-in"
            self.settings["target_dir"] = self.target_dir
            config.save_settings(self.settings)

        if not os.path.exists(self.target_dir):
            try:
                os.makedirs(self.target_dir)
            except Exception:
                pass

        self.steam_path = self._ensure_steam_path()

    def _ensure_steam_path(self):
        saved_path = self.settings.get("steam_path", "")
        if saved_path and os.path.isdir(saved_path):
            return saved_path

        detected_path = steam_utils.find_steam_install_path()
        if detected_path:
            self.settings["steam_path"] = detected_path
            config.save_settings(self.settings)
        return detected_path

    def save_config(self):
        self.settings["theme"] = self.current_theme
        self.settings["text_color"] = self.current_text_color
        self.settings["target_dir"] = self.target_dir
        config.save_settings(self.settings)

    def load_images(self):
        self.img_logo, self.icon_settings, self.icon_back, self.icon_discord = None, None, None, None
        self.img_logo_mini = None
        self.tray_pil_image = None

        try:
            logo_data = image_utils.load_pil_image(config.LOGO_FILENAME)
            self.img_logo = ctk.CTkImage(light_image=logo_data, dark_image=logo_data, size=(60, 60))

            self._mini_glow_base = logo_data.copy()
            self.img_logo_mini = self._build_mini_logo_image()
        except Exception:
            pass

        try:
            ico_path = config.APP_ICON
            if os.path.exists(ico_path):
                self.iconbitmap(default=ico_path)

            self.iconphoto(
                True,
                ImageTk.PhotoImage(logo_data.resize((256, 256), Image.LANCZOS)),
                ImageTk.PhotoImage(logo_data.resize((64, 64), Image.LANCZOS)),
                ImageTk.PhotoImage(logo_data.resize((48, 48), Image.LANCZOS)),
                ImageTk.PhotoImage(logo_data.resize((32, 32), Image.LANCZOS)),
                ImageTk.PhotoImage(logo_data.resize((16, 16), Image.LANCZOS))
            )
            self.tray_pil_image = logo_data.resize(config.TRAY_ICON_SIZE, Image.LANCZOS)
            self._taskbar_ico_path = ico_path
            self.after(250, self._reapply_taskbar_icon)
        except Exception:
            pass

        try:
            settings_data = image_utils.load_pil_image(config.SETTINGS_ICON)
            self.icon_settings = ctk.CTkImage(light_image=settings_data, dark_image=settings_data, size=(20, 20))
        except Exception:
            pass

        try:
            back_data = image_utils.load_pil_image(config.BACK_ICON)
            self.icon_back = ctk.CTkImage(light_image=back_data, dark_image=back_data, size=(20, 20))
        except Exception:
            pass

        try:
            discord_data = image_utils.load_pil_image(config.DISCORD_ICON)
            self.icon_discord = ctk.CTkImage(light_image=discord_data, dark_image=discord_data, size=(20, 20))
        except Exception:
            pass

    def _get_ui_icon(self, icon_name, color, size=16):
        key = (icon_name, color.lower(), size)
        if key in self._ui_icon_cache:
            return self._ui_icon_cache[key]

        icon_path = config.resource_path("Pictures", "icons", f"{icon_name}.png")
        try:
            if icon_name in {"trash-2", "download", "search"}:
                source = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
                draw = ImageDraw.Draw(source)
                stroke = 8
                if icon_name == "trash-2":
                    draw.line((16, 24, 80, 24), fill="white", width=stroke)
                    draw.line((32, 16, 64, 16, 64, 24), fill="white", width=stroke, joint="curve")
                    draw.line((24, 28, 28, 80, 68, 80, 72, 28), fill="white", width=stroke, joint="curve")
                    draw.line((40, 42, 40, 68), fill="white", width=stroke)
                    draw.line((56, 42, 56, 68), fill="white", width=stroke)
                elif icon_name == "download":
                    draw.line((48, 12, 48, 56), fill="white", width=stroke)
                    draw.line((28, 40, 48, 60, 68, 40), fill="white", width=stroke, joint="curve")
                    draw.line((16, 64, 16, 80, 80, 80, 80, 64), fill="white", width=stroke, joint="curve")
                else:
                    draw.ellipse((16, 12, 62, 58), outline="white", width=stroke)
                    draw.line((54, 54, 80, 80), fill="white", width=stroke)
            else:
                source = Image.open(icon_path).convert("RGBA")
            tinted = Image.new("RGBA", source.size, _hex_to_rgb(color) + (0,))
            tinted.putalpha(source.getchannel("A"))
            icon = ctk.CTkImage(light_image=tinted, dark_image=tinted, size=(size, size))
        except Exception:
            icon = None

        self._ui_icon_cache[key] = icon
        return icon

    def init_ui(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.pack(fill="both", expand=True)

        self.header_zone = ctk.CTkFrame(self.main_frame, corner_radius=8)
        self.header_zone.pack(side="top", fill="x", padx=20, pady=20)

        if self.img_logo:
            self.logo_label = ctk.CTkLabel(self.header_zone, image=self.img_logo, text="")
        else:
            self.logo_label = ctk.CTkLabel(self.header_zone, text="[Logo]", font=(FONT, 14, "bold"))

        self.logo_label.pack(side="left", padx=15, pady=15)
        self.logo_label.bind("<Double-Button-1>", self.toggle_mini_mode)

        self.title_label = ctk.CTkLabel(self.header_zone, text="Pizza Tools", font=(FONT, 22, "bold"))
        self.title_label.pack(side="left", pady=15)

        self.main_nav = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.main_nav.pack(side="top", fill="x", padx=20, pady=(0, 12))
        self.main_nav_buttons = {}
        self.main_nav_icons = {"Home": "house", "Games": "gamepad-2", "Fixes": "download", "Settings": "settings"}
        for column, label in enumerate(("Home", "Games", "Fixes", "Settings")):
            self.main_nav.grid_columnconfigure(column, weight=1, uniform="main_navigation")
            button = ctk.CTkButton(
                self.main_nav, text=label, image=self._get_ui_icon(
                    self.main_nav_icons[label], config.TEXT_COLORS.get(self.current_text_color, "#ffffff"), 16
                ), compound="left", width=100, height=34, font=(FONT, 11, "bold"),
                command=lambda destination=label: self.navigate_to(destination)
            )
            button.grid(row=0, column=column, sticky="ew", padx=3)
            self.main_nav_buttons[label] = button

        self.footer_zone = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.footer_zone.pack(side="bottom", fill="x", padx=20, pady=(0, 20))

        self.discord_btn = ctk.CTkButton(
            self.footer_zone, text=" Join our Discord", image=self.icon_discord,
            fg_color="#5865F2", hover_color="#4752C4", text_color="white",
            font=(FONT, 13, "bold"), command=self.open_discord
        )
        self.discord_btn.pack(pady=5)

        self.status_zone = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.status_zone.pack(side="bottom", fill="x", padx=20, pady=(0, 10))

        self.status_label = ctk.CTkLabel(self.status_zone, text="Waiting for files...", font=(FONT, 12, "bold"))
        self.status_label.pack(pady=(0, 5))

        self.progress_bar = ctk.CTkProgressBar(self.status_zone, height=8)
        self.progress_bar.pack(fill="x", padx=10)
        self.progress_bar.set(0)

        self.content_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True)

        self.uploader_view = ctk.CTkFrame(self.content_container, corner_radius=12)
        self.uploader_view.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.drop_label = ctk.CTkLabel(self.uploader_view, text="Drag & Drop files or folders here\n\n(.lua, .manifest, .zip, .rar, .7z or Online-Fix folder)",
                                       font=(FONT, 16, "bold"))
        self.drop_label.pack(expand=True)

        self.games_view = ctk.CTkScrollableFrame(self.content_container, corner_radius=12)
        for col in range(2):
            self.games_view.grid_columnconfigure(col, weight=1)
        self.games_title = ctk.CTkLabel(self.games_view, text="Your Games", font=(FONT, 20, "bold"))
        self.games_title.pack(anchor="w", padx=18, pady=(18, 14))
        self.games_search_row = ctk.CTkFrame(self.games_view, fg_color="transparent")
        self.games_search_row.pack(fill="x", padx=18, pady=(0, 10))
        self.games_search_icon = ctk.CTkLabel(
            self.games_search_row,
            image=self._get_ui_icon("search", "#aebbd0", 15),
            text="",
        )
        self.games_search_icon.pack(side="left", padx=(0, 8))
        self.games_search_var = tk.StringVar()
        self.games_search_entry = ctk.CTkEntry(
            self.games_search_row, placeholder_text="Search by game or App ID",
            height=32, font=(FONT, 10), textvariable=self.games_search_var
        )
        self.games_search_entry.pack(side="left", fill="x", expand=True)
        self.games_search_var.trace_add("write", lambda *_: self._schedule_game_search())
        self.games_toolbar = ctk.CTkFrame(self.games_view, fg_color="transparent")
        self.games_toolbar.pack(fill="x", padx=18, pady=(0, 10))
        self.games_count_label = ctk.CTkLabel(self.games_toolbar, text="0 games", font=(FONT, 11, "bold"))
        self.games_count_label.pack(side="left")
        self.games_refresh_btn = ctk.CTkButton(
            self.games_toolbar, text="Refresh", width=76, height=28,
            font=(FONT, 11, "bold"), command=self.refresh_games
        )
        self.games_refresh_btn.pack(side="right")
        self.games_grid = ctk.CTkFrame(self.games_view, fg_color="transparent")
        self.games_grid.pack(fill="both", expand=True, padx=12, pady=(0, 18))
        for col in range(2):
            self.games_grid.grid_columnconfigure(col, weight=1)
        self._game_card_refs = {}
        self._game_cover_cache_dir = os.path.join(config.CONFIG_DIR, "covers")

        self.downloader_view = ctk.CTkFrame(self.content_container, corner_radius=12)
        self.onlinefix_title = ctk.CTkLabel(
            self.downloader_view, text="Online-Fix Downloader", font=(FONT, 19, "bold")
        )
        self.onlinefix_title.pack(anchor="w", padx=16, pady=(15, 1))
        self.onlinefix_subtitle = ctk.CTkLabel(
            self.downloader_view, text="Search for a game and save its fix to Downloads.",
            font=(FONT, 10), anchor="w"
        )
        self.onlinefix_subtitle.pack(anchor="w", padx=16, pady=(0, 10))

        self.onlinefix_requirements_panel = ctk.CTkFrame(self.downloader_view, corner_radius=10)
        self.onlinefix_requirements_panel.pack(fill="x", padx=14, pady=(0, 12))
        self.onlinefix_requirements_label = ctk.CTkLabel(
            self.onlinefix_requirements_panel, text="Requirements not checked yet",
            font=(FONT, 11, "bold"), anchor="w"
        )
        self.onlinefix_requirements_label.pack(fill="x", padx=12, pady=(9, 2))
        self.onlinefix_requirements_help = ctk.CTkLabel(
            self.onlinefix_requirements_panel, text="Playwright and its Chromium browser are required.",
            font=(FONT, 9), anchor="w", justify="left", wraplength=340
        )
        self.onlinefix_requirements_help.pack(fill="x", padx=12, pady=(0, 9))

        self.onlinefix_input_label = ctk.CTkLabel(
            self.downloader_view, text="GAME NAME", font=(FONT, 9, "bold"), anchor="w"
        )
        self.onlinefix_input_label.pack(fill="x", padx=16, pady=(0, 5))
        self.onlinefix_input_row = ctk.CTkFrame(self.downloader_view, fg_color="transparent")
        self.onlinefix_input_row.pack(fill="x", padx=14, pady=(0, 9))
        self.onlinefix_game_entry = ctk.CTkEntry(
            self.onlinefix_input_row, placeholder_text="e.g. Left 4 Dead 2", height=34,
            font=(FONT, 11)
        )
        self.onlinefix_game_entry.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self.onlinefix_game_entry.bind("<Return>", lambda _event: self._start_onlinefix_download())
        self.onlinefix_start_btn = ctk.CTkButton(
            self.onlinefix_input_row, text="Download", width=104, height=34,
            font=(FONT, 10, "bold"), image=self._get_ui_icon("download", "#ffffff", 15),
            compound="left", state="disabled", command=self._start_onlinefix_download
        )
        self.onlinefix_start_btn.pack(side="right")

        self.onlinefix_progress = ctk.CTkProgressBar(self.downloader_view, height=5, corner_radius=0)
        self.onlinefix_progress.pack(fill="x", padx=16, pady=(0, 8))
        self.onlinefix_progress.set(0)
        self.onlinefix_log = ctk.CTkTextbox(
            self.downloader_view, height=155, corner_radius=9, font=("Consolas", 9), wrap="word"
        )
        self.onlinefix_log.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self.onlinefix_log.configure(state="disabled")
        self.onlinefix_downloads_btn = ctk.CTkButton(
            self.downloader_view, text="Open Downloads", width=125, height=29,
            font=(FONT, 9, "bold"), image=self._get_ui_icon("folder-open", "#ffffff", 14),
            compound="left", command=self._open_downloads_folder
        )
        self.onlinefix_downloads_btn.pack(anchor="e", padx=14, pady=(0, 12))

        self.settings_view = ctk.CTkFrame(self.content_container, corner_radius=12)
        self.settings_category_bar = ctk.CTkFrame(self.settings_view, fg_color="transparent")
        self.settings_category_bar.pack(fill="x", padx=12, pady=(12, 8))
        self.settings_categories = {
            "Design": ctk.CTkScrollableFrame(self.settings_view, corner_radius=10),
            "Files": ctk.CTkScrollableFrame(self.settings_view, corner_radius=10),
            "App": ctk.CTkScrollableFrame(self.settings_view, corner_radius=10),
            "Steam": ctk.CTkScrollableFrame(self.settings_view, corner_radius=10),
        }
        self.settings_category_buttons = {}
        self.settings_category_icons = {
            "Design": "palette", "Files": "folder-open", "App": "monitor-cog", "Steam": "steam"
        }
        for column, category in enumerate(self.settings_categories):
            self.settings_category_bar.grid_columnconfigure(column, weight=1, uniform="settings_categories")
            button = ctk.CTkButton(
                self.settings_category_bar, text=category, image=self._get_ui_icon(
                    self.settings_category_icons[category], config.TEXT_COLORS.get(self.current_text_color, "#ffffff"), 14
                ), compound="left", width=82, height=30,
                font=(FONT, 10, "bold"), command=lambda name=category: self.show_settings_category(name)
            )
            button.grid(row=0, column=column, sticky="ew", padx=3)
            self.settings_category_buttons[category] = button

        self.theme_label = ctk.CTkLabel(self.settings_categories['Design'], text="Theme Color", font=(FONT, 13, "bold"))
        self.theme_label.pack(anchor="w", padx=25, pady=(15, 5))
        self.theme_menu = ctk.CTkOptionMenu(self.settings_categories['Design'], values=list(config.THEMES.keys()),
                                            command=self.change_theme,
                                            font=(FONT, 12, "bold"), width=200,
                                            corner_radius=SMALL_CORNER, height=32)
        self.theme_menu.pack(anchor="w", padx=25, pady=(0, 15))
        self.theme_menu.set(self.current_theme)

        self.text_label = ctk.CTkLabel(self.settings_categories['Design'], text="Text Color", font=(FONT, 13, "bold"))
        self.text_label.pack(anchor="w", padx=25, pady=(0, 5))
        self.text_menu = ctk.CTkOptionMenu(self.settings_categories['Design'], values=list(config.TEXT_COLORS.keys()),
                                           command=self.change_text_color, font=(FONT, 12, "bold"), width=200,
                                           corner_radius=SMALL_CORNER, height=32)
        self.text_menu.pack(anchor="w", padx=25, pady=(0, 15))
        self.text_menu.set(self.current_text_color)

        self.custom_colors_label = ctk.CTkLabel(self.settings_categories['Design'], text="Custom Theme Colors", font=(FONT, 13, "bold"))
        self.custom_colors_label.pack(anchor="w", padx=25, pady=(15, 2))
        ctk.CTkLabel(self.settings_categories['Design'], text="Select a color to edit it.", font=(FONT, 11),
                     text_color="#B8C0CC").pack(anchor="w", padx=25, pady=(0, 8))

        self.color_buttons = {}
        self.theme_color_labels = {
            "bg": "Background", "card": "Card", "accent": "Accent",
            "btn": "Button", "btn_hover": "Button Hover",
        }

        for key, label in self.theme_color_labels.items():
            color_frame = ctk.CTkFrame(self.settings_categories['Design'], fg_color="transparent")
            color_frame.pack(fill="x", padx=25, pady=(0, 6))

            color_label = ctk.CTkLabel(color_frame, text=label, font=(FONT, 11))
            color_label.pack(side="left")

            button = ctk.CTkButton(color_frame, text="", font=(FONT, 11, "bold"), width=102, height=28,
                                   corner_radius=SMALL_CORNER, border_width=1,
                                   command=lambda key=key: self.edit_theme_color(key))
            button.pack(side="right")
            tk.Frame.configure(button, takefocus=True)
            tk.Frame.bind(button, "<Return>", lambda event, key=key: self.edit_theme_color(key))
            tk.Frame.bind(button, "<space>", lambda event, key=key: self.edit_theme_color(key))
            tk.Frame.bind(button, "<FocusIn>", lambda event, button=button: button.configure(border_color="#91B9FF"))
            tk.Frame.bind(button, "<FocusOut>", lambda event, button=button: button.configure(border_color="#758195"))
            self.color_buttons[key] = button

        self.reset_colors_btn = ctk.CTkButton(self.settings_categories['Design'], text="Reset to Default",
                                              font=(FONT, 11, "bold"), command=self.reset_custom_colors)
        self.reset_colors_btn.pack(anchor="w", padx=25, pady=(8, 20))

        self.path_label = ctk.CTkLabel(self.settings_categories['Files'], text="Save Folder", font=(FONT, 13, "bold"))
        self.path_label.pack(anchor="w", padx=25, pady=(15, 5))

        path_frame = ctk.CTkFrame(self.settings_categories['Files'], fg_color="transparent")
        path_frame.pack(fill="x", padx=25, pady=(0, 15))
        self.path_entry = ctk.CTkEntry(path_frame, font=(FONT, 11), corner_radius=SMALL_CORNER, height=32)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.path_entry.insert(0, self.target_dir)
        self.path_entry.configure(state="disabled")

        self.path_btn = ctk.CTkButton(path_frame, text="Browse", width=60, font=(FONT, 11, "bold"),
                                      corner_radius=SMALL_CORNER, command=self.browse_path)
        self.path_btn.pack(side="right")

        self.rar_cleanup_label = ctk.CTkLabel(self.settings_categories['Files'], text="RAR Cleanup",
                                              font=(FONT, 13, "bold"))
        self.rar_cleanup_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.rar_cleanup_switch = ctk.CTkSwitch(self.settings_categories['Files'],
                                                text="Delete RAR after successful patch",
                                                font=(FONT, 12), command=self.toggle_delete_rar_after_patch)
        self.rar_cleanup_switch.pack(anchor="w", padx=25, pady=(0, 15))

        if self.settings.get("delete_rar_after_patch", False):
            self.rar_cleanup_switch.select()

        self.zip_cleanup_label = ctk.CTkLabel(self.settings_categories['Files'], text="ZIP Cleanup",
                                              font=(FONT, 13, "bold"))
        self.zip_cleanup_label.pack(anchor="w", padx=25, pady=(0, 5))
        self.zip_cleanup_switch = ctk.CTkSwitch(self.settings_categories['Files'],
                                                text="Delete ZIP after successful extraction",
                                                font=(FONT, 12), command=self.toggle_delete_zip_after_extract)
        self.zip_cleanup_switch.pack(anchor="w", padx=25, pady=(0, 15))

        if self.settings.get("delete_zip_after_extract", False):
            self.zip_cleanup_switch.select()

        self.remove_game_label = ctk.CTkLabel(self.settings_categories['Files'], text="Remove Game (by Game ID)",
                                              font=(FONT, 13, "bold"))
        self.remove_game_label.pack(anchor="w", padx=25, pady=(5, 5))

        remove_game_frame = ctk.CTkFrame(self.settings_categories['Files'], fg_color="transparent")
        remove_game_frame.pack(fill="x", padx=25, pady=(0, 15))
        self.remove_game_entry = ctk.CTkEntry(remove_game_frame, font=(FONT, 11), placeholder_text="Game ID, e.g. 67",
                                              corner_radius=SMALL_CORNER, height=32)
        self.remove_game_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.remove_game_entry.bind("<Return>", lambda event: self.remove_game())

        self.remove_game_btn = ctk.CTkButton(remove_game_frame, text="Remove", width=60,
                                             font=(FONT, 11, "bold"), corner_radius=SMALL_CORNER,
                                             command=self.remove_game)
        self.remove_game_btn.pack(side="right")

        self.autostart_label = ctk.CTkLabel(self.settings_categories['App'], text="System Startup", font=(FONT, 13, "bold"))
        self.autostart_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.autostart_switch = ctk.CTkSwitch(self.settings_categories['App'], text="Launch app on PC startup", font=(FONT, 12),
                                              command=self.toggle_autostart)
        self.autostart_switch.pack(anchor="w", padx=25, pady=(0, 15))

        if windows_integration.is_autostart_enabled(config.REG_APP_NAME):
            self.autostart_switch.select()

        self.shortcut_label = ctk.CTkLabel(self.settings_categories['App'], text="Desktop Shortcut", font=(FONT, 13, "bold"))
        self.shortcut_label.pack(anchor="w", padx=25, pady=(0, 5))
        self.shortcut_btn = ctk.CTkButton(self.settings_categories['App'], text="Create Desktop Shortcut",
                                          font=(FONT, 12, "bold"), command=self.create_desktop_shortcut)
        self.shortcut_btn.pack(anchor="w", padx=25, pady=(0, 15))

        self.discord_rpc_label = ctk.CTkLabel(self.settings_categories['App'], text="Discord Rich Presence",
                                              font=(FONT, 13, "bold"))
        self.discord_rpc_label.pack(anchor="w", padx=25, pady=(0, 5))
        self.discord_rpc_switch = ctk.CTkSwitch(self.settings_categories['App'], text="Show activity on Discord profile",
                                                font=(FONT, 12), command=self.toggle_discord_rpc)
        self.discord_rpc_switch.pack(anchor="w", padx=25, pady=(0, 25))

        if self.settings.get("discord_rpc", False):
            self.discord_rpc_switch.select()


        self.update_label = ctk.CTkLabel(self.settings_categories['App'], text="App Version", font=(FONT, 13, "bold"))
        self.update_label.pack(anchor="w", padx=25, pady=(5, 5))

        update_row = ctk.CTkFrame(self.settings_categories['App'], fg_color="transparent")
        update_row.pack(fill="x", padx=25, pady=(0, 20))

        self.version_label = ctk.CTkLabel(
            update_row,
            text=f"v{config.APP_VERSION}",
            font=(FONT, 12),
        )
        self.version_label.pack(side="left", padx=(0, 12))

        self.check_update_btn = ctk.CTkButton(
            update_row,
            text="Check for Updates",
            font=(FONT, 12, "bold"),
            width=170,
            corner_radius=SMALL_CORNER,
            height=32,
            command=self.manual_update_check,
        )
        self.check_update_btn.pack(side="left", padx=(0, 10))

        self.github_btn = ctk.CTkButton(
            update_row,
            text="GitHub Repo",
            font=(FONT, 12, "bold"),
            width=130,
            corner_radius=SMALL_CORNER,
            height=32,
            command=self.open_github,
        )
        self.github_btn.pack(side="left")

        self.steam_patch_label = ctk.CTkLabel(self.settings_categories['Steam'], text="BetterSteamTools Patch",
                                              font=(FONT, 13, "bold"))
        self.steam_patch_label.pack(anchor="w", padx=25, pady=(0, 5))
        self.steam_patch_btn = ctk.CTkButton(self.settings_categories['Steam'], text="Apply Patch",
                                             font=(FONT, 12, "bold"), command=self.apply_steam_patch)
        self.steam_patch_btn.pack(anchor="w", padx=25, pady=(0, 15))

        self.steam_control_label = ctk.CTkLabel(self.settings_categories['Steam'], text="Steam Control",
                                                font=(FONT, 13, "bold"))
        self.steam_control_label.pack(anchor="w", padx=25, pady=(0, 5))

        steam_control_frame = ctk.CTkFrame(self.settings_categories['Steam'], fg_color="transparent")
        steam_control_frame.pack(fill="x", padx=25, pady=(0, 25))

        self.steam_action_btn = ctk.CTkButton(steam_control_frame, text=self._steam_action_label_text(),
                                              font=(FONT, 12, "bold"), command=self.handle_steam_action)
        self.steam_action_btn.pack(side="left", padx=(0, 10))

        self.steam_close_btn = ctk.CTkButton(steam_control_frame, text="Close Steam",
                                             font=(FONT, 12, "bold"), command=self.handle_close_steam)
        self.steam_close_btn.pack(side="left")
        self.show_settings_category("Design")

        self.mini_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=config.TRANSPARENT_KEY,
                                       border_width=0)

        mini_logo_image = self.img_logo_mini if self.img_logo_mini else self.img_logo
        if mini_logo_image:
            self.mini_logo = ctk.CTkLabel(self.mini_frame, image=mini_logo_image, text="",
                                          fg_color=config.TRANSPARENT_KEY)
        else:
            self.mini_logo = ctk.CTkLabel(self.mini_frame, text="[Logo]", font=(FONT, 16, "bold"),
                                          fg_color=config.TRANSPARENT_KEY)
        self.mini_logo.place(relx=0.5, rely=0.4, anchor="center")

        self.mini_status = ctk.CTkLabel(self.mini_frame, text="", font=(FONT, 9, "bold"),
                                        corner_radius=6, text_color="#ffffff",
                                        fg_color="#181818", padx=8, pady=3)

        self.mini_logo.bind("<Double-Button-1>", self.toggle_mini_mode)
        self.mini_frame.bind("<Double-Button-1>", self.toggle_mini_mode)
        self.mini_status.bind("<Double-Button-1>", self.toggle_mini_mode)

        self.mini_logo.bind("<Button-3>", self.show_mini_context_menu)
        self.mini_frame.bind("<Button-3>", self.show_mini_context_menu)
        self.mini_status.bind("<Button-3>", self.show_mini_context_menu)

        self.mini_logo.bind("<ButtonPress-1>", self.start_move)
        self.mini_logo.bind("<B1-Motion>", self.do_move)
        self.mini_frame.bind("<ButtonPress-1>", self.start_move)
        self.mini_frame.bind("<B1-Motion>", self.do_move)
        self.mini_status.bind("<ButtonPress-1>", self.start_move)
        self.mini_status.bind("<B1-Motion>", self.do_move)

        self.uploader_view.drop_target_register(DND_FILES)
        self.uploader_view.dnd_bind('<<Drop>>', self.handle_drop)

        self.mini_frame.drop_target_register(DND_FILES)
        self.mini_frame.dnd_bind('<<Drop>>', self.handle_drop)

        self.mini_status.drop_target_register(DND_FILES)
        self.mini_status.dnd_bind('<<Drop>>', self.handle_drop)

    def _apply_custom_theme_color(self):
        hex_color = self.custom_color_entry.get().strip()

        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color

        if len(hex_color) != 7:
            self.trigger_status_message("Invalid hex color format. Use #RRGGBB", "Invalid")
            return

        try:
            int(hex_color[1:], 16)
        except ValueError:
            self.trigger_status_message("Invalid hex color. Use #RRGGBB", "Invalid")
            return

        self.settings["custom_theme_color"] = hex_color
        self.save_config()
        self.trigger_status_message(f"Custom theme color applied: {hex_color}", "Applied")

    def _reapply_taskbar_icon(self):
        ico_path = getattr(self, "_taskbar_ico_path", None)
        if not ico_path or not os.path.exists(ico_path):
            return

        try:
            self.iconbitmap(default=ico_path)
        except Exception:
            pass

        try:
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE = 0x00000040
            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1

            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = user32.GetAncestor(self.winfo_id(), 2)
            if not hwnd:
                hwnd = self.winfo_id()

            cx_sm = user32.GetSystemMetrics(49)
            cy_sm = user32.GetSystemMetrics(50)
            cx_big = user32.GetSystemMetrics(11)
            cy_big = user32.GetSystemMetrics(12)

            h_icon_big = user32.LoadImageW(
                None, ico_path, IMAGE_ICON, cx_big, cy_big, LR_LOADFROMFILE
            )
            h_icon_small = user32.LoadImageW(
                None, ico_path, IMAGE_ICON, cx_sm, cy_sm, LR_LOADFROMFILE
            )

            if h_icon_big:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)
            if h_icon_small:
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_small)
        except Exception:
            pass

    def start_move(self, event):
        self.x_click = event.x
        self.y_click = event.y

    def do_move(self, event):
        x = self.winfo_x() - self.x_click + event.x
        y = self.winfo_y() - self.y_click + event.y
        self.geometry(f"+{x}+{y}")

    def show_mini_context_menu(self, event):
        self.close_context_menu()

        t = config.THEMES.get(self.current_theme, config.THEMES["Dark"])

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=config.TRANSPARENT_KEY)
        try:
            popup.attributes("-transparentcolor", config.TRANSPARENT_KEY)
        except Exception:
            pass

        card = ctk.CTkFrame(popup, corner_radius=10, fg_color=t["card"],
                            border_width=1, border_color=t["accent"])
        card.pack(padx=1, pady=1)

        def make_item(label_text, command, is_last=False):
            item = ctk.CTkButton(
                card, text=label_text, anchor="w", corner_radius=6,
                fg_color="transparent", hover_color=t["accent"],
                text_color=config.TEXT_COLORS.get(self.current_text_color, "#ffffff"),
                font=(FONT, 12), height=32, width=190,
                command=lambda: self._run_context_action(popup, command)
            )
            item.pack(fill="x", padx=6, pady=(6 if not is_last else 3, 3 if not is_last else 6))
            return item

        make_item("Switch to App", self.toggle_mini_mode)
        make_item("Run in Background", self.minimize_to_tray)
        make_item(f"{self._steam_action_label_text()}", self.handle_steam_action)
        make_item("Close Steam", self.handle_close_steam)
        make_item("Exit App", self.exit_app, is_last=True)

        popup.update_idletasks()
        w = popup.winfo_reqwidth()
        h = popup.winfo_reqheight()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = min(event.x_root, screen_w - w - 10)
        y = min(event.y_root, screen_h - h - 10)
        popup.geometry(f"{w}x{h}+{x}+{y}")

        self.context_popup = popup
        popup.bind("<FocusOut>", lambda e: self.close_context_menu())
        popup.focus_force()

    def _run_context_action(self, popup, command):
        self.close_context_menu()
        command()

    def close_context_menu(self):
        popup = getattr(self, "context_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass
            self.context_popup = None

    def toggle_mini_mode(self, event=None):
        try:
            self.close_context_menu()

            self.withdraw()

            if not self.is_mini_mode:
                self.is_mini_mode = True
                self.main_frame.pack_forget()

                self.overrideredirect(True)
                self.attributes("-topmost", True)
                self.attributes("-transparentcolor", config.TRANSPARENT_KEY)

                x = self.winfo_x() + 150
                y = self.winfo_y() + 200
                self.minsize(0, 0)
                self.geometry(f"160x100+{x}+{y}")

                self.mini_frame.pack(fill="both", expand=True)
            else:
                self.is_mini_mode = False
                self.mini_frame.pack_forget()

                self.attributes("-transparentcolor", "")
                self.overrideredirect(False)
                self.attributes("-topmost", False)

                x = self.winfo_x() - 150
                y = self.winfo_y() - 200
                self.minsize(450, 700)
                self.geometry(f"450x700+{x}+{y}")

                self.main_frame.pack(fill="both", expand=True)
                try:
                    self.apply_theme()
                except Exception:
                    pass

            self.update_idletasks()
            self.deiconify()
        except Exception as e:
            pass

    def minimize_to_tray(self):
        self.withdraw()

        if self.tray_icon is not None:
            return

        image = self.tray_pil_image
        if image is None:
            image = Image.new("RGBA", (64, 64), (43, 43, 43, 255))

        def on_show(icon, item):
            icon.stop()
            self.tray_icon = None
            self.after(0, self.restore_from_tray)

        def on_quit(icon, item):
            icon.stop()
            self.tray_icon = None
            self.after(0, self.on_close)

        self.tray_icon = windows_integration.create_tray_icon(image, on_show, on_quit)

        if self.tray_icon is None:
            try:
                self.overrideredirect(False)
                self.iconify()
                self.deiconify()
            except Exception:
                pass
            self.trigger_status_message(
                "pystray is missing -> pip install pystray", "No Tray"
            )
            return

        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def restore_from_tray(self):
        self.deiconify()
        if self.is_mini_mode:
            self.attributes("-topmost", True)

    def toggle_discord_rpc(self):
        enabled = self.discord_rpc_switch.get() == 1
        self.settings["discord_rpc"] = enabled
        self.save_config()
        if enabled:
            self.start_discord_rpc()
        else:
            self.stop_discord_rpc()

    def toggle_delete_zip_after_extract(self):
        enabled = self.zip_cleanup_switch.get() == 1
        self.settings["delete_zip_after_extract"] = enabled
        self.save_config()

    def toggle_delete_rar_after_patch(self):
        enabled = self.rar_cleanup_switch.get() == 1
        self.settings["delete_rar_after_patch"] = enabled
        self.save_config()

    def edit_theme_color(self, key):
        def finish(color):
            if color is not None:
                colors = dict(self.settings.get("custom_colors") or {})
                colors[key] = color
                self.settings["custom_colors"] = colors
                self.save_config()
            self.apply_theme()
            tk.Frame.focus_set(self.color_buttons[key])

        ThemeColorPicker(
            self, self.theme_color_labels[key], self.active_theme_colors[key],
            preview=lambda color: self.apply_theme(preview_color=(key, color)), finish=finish,
        )

    def reset_custom_colors(self):
        self.settings["custom_colors"] = dict.fromkeys(self.theme_color_labels)
        self.save_config()
        self.apply_theme()
        self.trigger_status_message("Colors reset to default", "Reset")

    def apply_steam_patch(self):
        steam_path = self._ensure_steam_path()
        self.steam_path = steam_path

        if not steam_path:
            self.trigger_status_message("Steam installation not found.", "No Steam")
            return

        if not os.path.isdir(config.PATCH_DIR):
            self.trigger_status_message("Patch folder not found next to the app.", "No Patch folder")
            return

        if steam_utils.is_steam_running():
            self.trigger_status_message("Please close Steam before patching.", "Steam is running")
            return

        confirmed = messagebox.askyesno(
            "Apply BetterSteamTools Patch",
            f"This will copy the patch files into:\n{steam_path}\n\n"
            "Existing files with the same name will be overwritten. Continue?"
        )
        if not confirmed:
            return

        copied_count, errors = patch_utils.copy_patch_files(config.PATCH_DIR, steam_path)

        if copied_count > 0 and not errors:
            self.trigger_status_message(f"Patch applied ({copied_count} file(s)).", "Patched!")
        elif copied_count > 0 and errors:
            self.trigger_status_message(
                f"Patched {copied_count} file(s), {len(errors)} error(s).", "Partial patch"
            )
        else:
            self.trigger_status_message("No patch files were applied.", "Patch failed")

    def _steam_action_label_text(self):
        return "Restart Steam" if steam_utils.is_steam_running() else "Start Steam"

    def refresh_steam_action_button(self):
        if hasattr(self, "steam_action_btn"):
            self.steam_action_btn.configure(text=self._steam_action_label_text())

    def handle_steam_action(self):
        steam_path = self._ensure_steam_path()
        self.steam_path = steam_path

        if not steam_path:
            self.trigger_status_message("Steam installation not found.", "No Steam")
            return

        steam_exe = os.path.join(steam_path, "steam.exe")
        if not os.path.isfile(steam_exe):
            self.trigger_status_message("steam.exe not found in the Steam folder.", "No steam.exe")
            return

        was_running = steam_utils.is_steam_running()
        self.trigger_status_message(
            "Restarting Steam..." if was_running else "Starting Steam...",
            "Restarting..." if was_running else "Starting...",
            delay_ms=8000
        )

        def worker():
            result = steam_utils.start_or_restart_steam(steam_exe)
            self.after(0, lambda: self._on_steam_action_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_steam_action_done(self, result):
        messages = {
            "started": ("Steam started.", "Started"),
            "restarted": ("Steam restarted.", "Restarted"),
            "error": ("Failed to start/restart Steam.", "Error"),
        }
        msg, mini_msg = messages.get(result, ("Steam action completed.", "Done"))
        self.trigger_status_message(msg, mini_msg)
        self.refresh_steam_action_button()

    def handle_close_steam(self):
        steam_path = self._ensure_steam_path()
        self.steam_path = steam_path

        if not steam_path:
            self.trigger_status_message("Steam installation not found.", "No Steam")
            return

        steam_exe = os.path.join(steam_path, "steam.exe")
        if not os.path.isfile(steam_exe):
            self.trigger_status_message("steam.exe not found in the Steam folder.", "No steam.exe")
            return

        if not steam_utils.is_steam_running():
            self.trigger_status_message("Steam is not running.", "Not running")
            return

        self.trigger_status_message("Closing Steam...", "Closing...", delay_ms=8000)

        def worker():
            result = steam_utils.close_steam(steam_exe)
            self.after(0, lambda: self._on_steam_close_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_steam_close_done(self, result):
        messages = {
            "closed": ("Steam closed.", "Closed"),
            "already_closed": ("Steam was already closed.", "Already closed"),
            "timeout": ("Steam did not close in time.", "Timeout"),
            "error": ("Failed to close Steam.", "Error"),
        }
        msg, mini_msg = messages.get(result, ("Steam action completed.", "Done"))
        self.trigger_status_message(msg, mini_msg)
        self.refresh_steam_action_button()

    def _poll_steam_status(self):
        if self.current_view == "settings" and getattr(self, "_selected_settings_category", "") == "Steam":
            try:
                self.refresh_steam_action_button()
            except Exception:
                pass

        try:
            self.after(10000, self._poll_steam_status)
        except Exception:
            pass

    def start_discord_rpc(self):
        success, error = self.discord.start()
        if not success and error:
            self.trigger_status_message(error, "RPC Fehler")

    def stop_discord_rpc(self):
        self.discord.stop()

    def on_close(self):
        self.exit_app()

    def exit_app(self):
        self.close_context_menu()
        self.stop_discord_rpc()
        if self._onlinefix_process is not None:
            try:
                self._onlinefix_process.terminate()
            except Exception:
                pass

        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

        self.destroy()

    def set_title_bar_color(self, hex_color):
        windows_integration.set_title_bar_color(self, hex_color)

    def change_theme(self, theme_name):
        self.current_theme = theme_name
        self.save_config()
        self.apply_theme()

    def change_text_color(self, color_name):
        self.current_text_color = color_name
        self.save_config()
        self.apply_theme()

    def browse_path(self):
        new_path = filedialog.askdirectory(initialdir=self.target_dir, title="Select Save Folder")
        if new_path:
            self.target_dir = os.path.normpath(new_path)
            self.path_entry.configure(state="normal")
            self.path_entry.delete(0, 'end')
            self.path_entry.insert(0, self.target_dir)
            self.path_entry.configure(state="disabled")
            self.save_config()
            self.trigger_status_message("Save path updated.", "Path updated")
            if self.current_view == "games":
                self.refresh_games()

    def remove_game(self):
        game_id = self.remove_game_entry.get().strip()
        if not game_id:
            self.trigger_status_message("Please enter a Game ID.", "No ID")
            return

        found_file = Game_remover.find_lua_file_for_game(self.target_dir, game_id)
        if not found_file:
            self.trigger_status_message(f"No file found for Game ID {game_id}.", "Not found")
            return

        confirmed = messagebox.askyesno(
            "Remove Game",
            f"Delete the following file?\n\n{found_file}\n\nThis cannot be undone."
        )
        if not confirmed:
            return

        if Game_remover.remove_lua_file(found_file):
            self.remove_game_entry.delete(0, 'end')
            self.trigger_status_message(f"Removed {os.path.basename(found_file)}.", "Removed")
        else:
            self.trigger_status_message("Failed to delete the file.", "Error")

    def apply_theme(self, theme_name=None, *, preview_color=None):
        if theme_name:
            self.current_theme = theme_name
        t = config.THEMES.get(self.current_theme, config.THEMES["Dark"]).copy()
        txt_col = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")

        custom_colors = self.settings.get("custom_colors", {})
        if custom_colors.get("bg"):
            t["bg"] = custom_colors["bg"]
        if custom_colors.get("card"):
            t["card"] = custom_colors["card"]
        if custom_colors.get("accent"):
            t["accent"] = custom_colors["accent"]
        if custom_colors.get("btn"):
            t["btn"] = custom_colors["btn"]
        if custom_colors.get("btn_hover"):
            t["btn_hover"] = custom_colors["btn_hover"]
        if preview_color is not None:
            key, color = preview_color
            t[key] = color

        self.active_theme_colors = t.copy()
        try:
            self.set_title_bar_color(t["bg"])
        except Exception:
            pass

        try:
            self.mini_status.configure(fg_color=t["card"])
        except Exception:
            pass

        try:
            self.main_frame.configure(fg_color=t["bg"])
            self.header_zone.configure(fg_color=t["card"])
            self.uploader_view.configure(fg_color=t["card"])
            self.settings_view.configure(fg_color=t["card"])
            self.downloader_view.configure(fg_color=t["card"])
            self.onlinefix_requirements_panel.configure(fg_color=t["bg"])
            for page in self.settings_categories.values():
                page.configure(fg_color=t["card"])
            self.games_view.configure(fg_color=t["card"])
        except Exception:
            pass

        try:
            self.progress_bar.configure(progress_color=t["btn"], fg_color=t["card"])
            self.status_label.configure(text_color=txt_col)
            self.title_label.configure(text_color=txt_col)
            self.version_label.configure(text_color=txt_col)
            self.drop_label.configure(text_color=txt_col)
        except Exception:
            pass

        try:
            self.path_entry.configure(text_color=txt_col, fg_color=t["bg"], border_color=t["accent"])
            self.remove_game_entry.configure(text_color=txt_col, fg_color=t["bg"], border_color=t["accent"])
            self.games_search_entry.configure(text_color=txt_col, fg_color=t["bg"], border_color=t["accent"])
        except Exception:
            pass

        for key, button in self.color_buttons.items():
            color = t[key]
            rgb = [channel / 255 for channel in _hex_to_rgb(color)]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                      for channel in rgb]
            luminance = sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
            foreground = "#000000" if luminance > 0.179 else "#FFFFFF"
            button.configure(text=color.upper(), fg_color=color, hover_color=color, text_color=foreground,
                             border_color="#758195")

        try:
            self.autostart_switch.configure(text_color=txt_col, progress_color=t["btn"])
            self.discord_rpc_switch.configure(text_color=txt_col, progress_color=t["btn"])
            self.zip_cleanup_switch.configure(text_color=txt_col, progress_color=t["btn"])
            self.rar_cleanup_switch.configure(text_color=txt_col, progress_color=t["btn"])
        except Exception:
            pass

        try:
            selected_nav = {
                "uploader": "Home", "games": "Games", "onlinefix": "Fixes", "settings": "Settings"
            }.get(self.current_view, "Home")
            self._update_main_navigation(selected_nav)
            self.show_settings_category(getattr(self, "_selected_settings_category", "Design"))
            self.discord_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.games_refresh_btn.configure(
                fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col,
                image=self._get_ui_icon("refresh-cw", txt_col, 14), compound="left"
            )
            self.path_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.reset_colors_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.remove_game_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.shortcut_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.check_update_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.steam_patch_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.steam_action_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.steam_close_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
            self.onlinefix_start_btn.configure(
                fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col,
                image=self._get_ui_icon("download", txt_col, 15)
            )
            self.onlinefix_downloads_btn.configure(
                fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col,
                image=self._get_ui_icon("folder-open", txt_col, 14)
            )
            self.onlinefix_game_entry.configure(
                text_color=txt_col, fg_color=t["bg"], border_color=t["accent"]
            )
            self.onlinefix_log.configure(
                text_color=txt_col, fg_color=t["bg"], border_color=t["accent"]
            )
            self.onlinefix_progress.configure(progress_color=t["btn"], fg_color=t["bg"])
            self.onlinefix_title.configure(text_color=txt_col)
            self.onlinefix_subtitle.configure(text_color="#aebbd0")
            self.onlinefix_requirements_label.configure(text_color=txt_col)
            self.onlinefix_requirements_help.configure(text_color="#aebbd0")
            self.onlinefix_input_label.configure(text_color="#aebbd0")
        except Exception:
            pass

        try:
            self.theme_menu.configure(fg_color=t["btn"], button_color=t["btn"], button_hover_color=t["btn_hover"],
                                      text_color=txt_col, dropdown_fg_color=t["card"], dropdown_hover_color=t["btn_hover"],
                                      dropdown_text_color=txt_col)
            self.text_menu.configure(fg_color=t["btn"], button_color=t["btn"], button_hover_color=t["btn_hover"],
                                     text_color=txt_col, dropdown_fg_color=t["card"], dropdown_hover_color=t["btn_hover"],
                                     dropdown_text_color=txt_col)
        except Exception:
            pass

        if preview_color is None:
            try:
                self._rebuild_mini_glow()
            except Exception:
                pass


    def _build_mini_logo_image(self):
        base = getattr(self, "_mini_glow_base", None)
        if base is None:
            return None

        logical = config.MINI_LOGO_SIZE[0]
        try:
            scaling = float(self._get_widget_scaling())
        except Exception:
            scaling = 1.0
        physical = round(logical * scaling)

        glow_img = image_utils.make_glow_logo(
            base, config.MINI_LOGO_SIZE, out_px=physical
        )
        self._mini_size = logical
        return ctk.CTkImage(light_image=glow_img, dark_image=glow_img, size=(logical, logical))

    def _rebuild_mini_glow(self):
        try:
            img = self._build_mini_logo_image()
            if img is None:
                return
            self.img_logo_mini = img
            if hasattr(self, "mini_logo"):
                self.mini_logo.configure(image=self.img_logo_mini)
        except Exception:
            pass

    def open_discord(self):
        webbrowser.open(config.DISCORD_LINK)

    def open_github(self):
        webbrowser.open(config.GITHUB_LINK)

    def _refresh_onlinefix_requirements(self):
        if self._onlinefix_requirements_checking:
            return
        self._onlinefix_requirements_checking = True
        self.onlinefix_requirements_label.configure(text="Checking requirements…", text_color="#fbbf24")
        self.onlinefix_requirements_help.configure(
            text="Checking Playwright, Chrome/Chromium and the downloader file."
        )
        self.onlinefix_start_btn.configure(state="disabled")

        def check():
            issues = []
            if not os.path.isfile(self._onlinefix_downloader_path):
                issues.append("Downloader file is missing")
            chrome_roots = (
                os.environ.get("PROGRAMFILES"),
                os.environ.get("PROGRAMFILES(X86)"),
                os.environ.get("LOCALAPPDATA"),
            )
            self._onlinefix_system_chrome = any(
                root and os.path.isfile(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
                for root in chrome_roots
            )
            if importlib.util.find_spec("playwright") is None:
                issues.append("Playwright is not installed")
            else:
                installed_browser = False
                try:
                    package_dir = os.path.dirname(importlib.util.find_spec("playwright").origin)
                    browsers_file = os.path.join(package_dir, "driver", "package", "browsers.json")
                    with open(browsers_file, "r", encoding="utf-8") as stream:
                        browser_manifest = json.load(stream)
                    browser_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
                    if browser_root == "0":
                        browser_root = os.path.join(package_dir, "driver", "package", ".local-browsers")
                    elif not browser_root:
                        browser_root = os.path.join(
                            os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local")),
                            "ms-playwright",
                        )
                    browser_names = {"chromium", "chromium-headless-shell"}
                    for item in browser_manifest.get("browsers", []):
                        if item.get("name") not in browser_names:
                            continue
                        folder = f"{item['name'].replace('-', '_')}-{item['revision']}"
                        candidate_folder = os.path.join(browser_root, folder)
                        executable_names = (
                            os.path.join("chrome-win", "chrome.exe"),
                            os.path.join("chrome-win64", "chrome.exe"),
                            os.path.join("chrome-headless-shell-win64", "headless_shell.exe"),
                            os.path.join("chrome-headless-shell-win32", "headless_shell.exe"),
                        )
                        if any(os.path.isfile(os.path.join(candidate_folder, name)) for name in executable_names):
                            installed_browser = True
                            break
                except Exception:
                    pass
                if not installed_browser and not self._onlinefix_system_chrome:
                    issues.append("Playwright Chromium or Google Chrome is not installed")
            self.after(0, lambda: self._show_onlinefix_requirements(issues))

        threading.Thread(target=check, daemon=True).start()

    def _show_onlinefix_requirements(self, issues):
        self._onlinefix_requirements_checking = False
        self._onlinefix_requirements_ready = not issues
        if issues:
            self.onlinefix_requirements_label.configure(
                text="Requirements missing · Downloader disabled", text_color="#fbbf24"
            )
            help_text = "Playwright: python -m pip install -r requirements.txt"
            if "Chromium" in " ".join(issues):
                help_text += "\nBrowser: install Google Chrome or run python -m playwright install chromium"
            if "Downloader file is missing" in issues:
                help_text += "\nThe Online-Fix downloader module is missing from src."
            self.onlinefix_requirements_help.configure(text=help_text)
            self.onlinefix_start_btn.configure(state="disabled")
        else:
            self.onlinefix_requirements_label.configure(
                text=("Ready · Playwright + Google Chrome detected" if self._onlinefix_system_chrome
                      else "Ready · Playwright Chromium detected"),
                text_color="#34d399"
            )
            self.onlinefix_requirements_help.configure(
                text="The downloader saves archives to your Windows Downloads folder."
            )
            if self._onlinefix_process is None:
                self.onlinefix_start_btn.configure(state="normal")

    def _append_onlinefix_log(self, text):
        self.onlinefix_log.configure(state="normal")
        self.onlinefix_log.insert("end", text + "\n")
        self.onlinefix_log.see("end")
        self.onlinefix_log.configure(state="disabled")

    def _start_onlinefix_download(self):
        if not self._onlinefix_requirements_ready or self._onlinefix_process is not None:
            return
        game_name = self.onlinefix_game_entry.get().strip()
        if not game_name:
            self._append_onlinefix_log("Enter a game name to begin.")
            return

        self.onlinefix_log.configure(state="normal")
        self.onlinefix_log.delete("1.0", "end")
        self.onlinefix_log.configure(state="disabled")
        self._append_onlinefix_log(f"Starting search for: {game_name}")
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                [sys.executable, "-X", "utf8", "-u", self._onlinefix_downloader_path],
                cwd=os.path.dirname(self._onlinefix_downloader_path),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
            self._onlinefix_process = process
            self.onlinefix_start_btn.configure(state="disabled")
            self.onlinefix_game_entry.configure(state="disabled")
            self.onlinefix_progress.configure(mode="indeterminate")
            self.onlinefix_progress.start()
            process.stdin.write(game_name.replace("\r", " ").replace("\n", " ") + "\n\n")
            process.stdin.flush()
            process.stdin.close()
            threading.Thread(target=self._read_onlinefix_output, args=(process,), daemon=True).start()
            self._drain_onlinefix_output()
        except Exception as error:
            self._onlinefix_process = None
            self.onlinefix_progress.stop()
            self.onlinefix_progress.configure(mode="determinate")
            self.onlinefix_progress.set(0)
            self.onlinefix_game_entry.configure(state="normal")
            self.onlinefix_start_btn.configure(state="normal")
            self._append_onlinefix_log(f"Could not start the downloader: {error}")

    def _read_onlinefix_output(self, process):
        try:
            for line in process.stdout:
                clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
                if clean:
                    self._onlinefix_output_queue.put(("line", clean))
        except Exception as error:
            self._onlinefix_output_queue.put(("line", f"Output error: {error}"))
        self._onlinefix_output_queue.put(("done", process.wait()))

    def _drain_onlinefix_output(self):
        finished = False
        while True:
            try:
                kind, value = self._onlinefix_output_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self._append_onlinefix_log(value)
            else:
                finished = True

        if finished:
            self._onlinefix_process = None
            self.onlinefix_progress.stop()
            self.onlinefix_progress.configure(mode="determinate")
            self.onlinefix_progress.set(0)
            self.onlinefix_game_entry.configure(state="normal")
            self.onlinefix_start_btn.configure(
                state="normal" if self._onlinefix_requirements_ready else "disabled"
            )
            self._append_onlinefix_log("Finished. Check the result above.")
        elif self._onlinefix_process is not None:
            self.after(120, self._drain_onlinefix_output)

    def _open_downloads_folder(self):
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            os.startfile(downloads_path)
        except Exception as error:
            self._append_onlinefix_log(f"Could not open Downloads: {error}")

    def switch_view(self):
        self.navigate_to("Home" if self.current_view == "settings" else "Settings")

    def navigate_to(self, destination):
        views = {
            "Home": ("uploader", self.uploader_view),
            "Games": ("games", self.games_view),
            "Fixes": ("onlinefix", self.downloader_view),
            "Settings": ("settings", self.settings_view),
        }
        if destination not in views:
            return

        view_name, target_view = views[destination]
        for view in (self.uploader_view, self.games_view, self.downloader_view, self.settings_view):
            view.pack_forget()

        if view_name in {"games", "onlinefix"}:
            self.status_zone.pack_forget()
            self.footer_zone.pack_forget()
        else:
            if not self.footer_zone.winfo_manager():
                self.footer_zone.pack(side="bottom", fill="x", padx=20, pady=(0, 20))
            if not self.status_zone.winfo_manager():
                self.status_zone.pack(side="bottom", fill="x", padx=20, pady=(0, 10))

        target_view.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.current_view = view_name
        self._update_main_navigation(destination)

        if view_name == "games":
            self.refresh_games()
        elif view_name == "onlinefix":
            self._refresh_onlinefix_requirements()
        elif view_name == "settings":
            self.refresh_steam_action_button()

    def show_games(self):
        self.navigate_to("Games")

    def _update_main_navigation(self, selected):
        colors = getattr(self, "active_theme_colors", config.THEMES.get(self.current_theme, config.THEMES["Dark"]))
        text_color = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")
        for label, button in self.main_nav_buttons.items():
            active = label == selected
            button.configure(
                fg_color=colors["btn"] if active else colors["card"],
                hover_color=colors["btn_hover"],
                text_color=text_color if active else "#b8c0cc",
                image=self._get_ui_icon(
                    self.main_nav_icons[label], text_color if active else "#b8c0cc", 16
                ),
            )

    def show_settings_category(self, category):
        if category not in self.settings_categories:
            return
        self._selected_settings_category = category
        if category == "Steam" and self.current_view == "settings":
            self.refresh_steam_action_button()
        selected_page = self.settings_categories[category]
        if selected_page.winfo_manager() != "pack":
            for page in self.settings_categories.values():
                page.pack_forget()
            selected_page.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        colors = getattr(self, "active_theme_colors", config.THEMES.get(self.current_theme, config.THEMES["Dark"]))
        text_color = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")
        for name, button in self.settings_category_buttons.items():
            active = name == category
            button.configure(
                fg_color=colors["btn"] if active else colors["bg"],
                hover_color=colors["btn_hover"],
                text_color=text_color if active else "#b8c0cc",
                image=self._get_ui_icon(
                    self.settings_category_icons[name], text_color if active else "#b8c0cc", 14
                ),
            )

    def refresh_games(self):
        games = []
        try:
            os.makedirs(self.target_dir, exist_ok=True)
            with os.scandir(self.target_dir) as entries:
                for entry in entries:
                    stem, ext = os.path.splitext(entry.name)
                    if ext.lower() != ".lua" or not stem.isdigit() or not entry.is_file(follow_symlinks=False):
                        continue
                    try:
                        file_stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    games.append({
                        "appid": stem,
                        "file_path": entry.path,
                        "file_state": (file_stat.st_size, file_stat.st_mtime_ns),
                    })
        except Exception as e:
            self.trigger_status_message(f"Couldn't read Lua folder: {e}", "Folder error")
            return

        games.sort(key=lambda game: int(game["appid"]))
        self._games_all_items = games
        self._apply_game_search()

    def _schedule_game_search(self, event=None):
        if self._games_search_after_id:
            try:
                self.after_cancel(self._games_search_after_id)
            except Exception:
                pass
        self._games_search_after_id = self.after(120, self._apply_game_search)

    def _apply_game_search(self):
        self._games_search_after_id = None
        query = self.games_search_entry.get().strip().casefold()
        self._current_game_filter_query = query
        all_games = self._games_all_items
        games = []
        for game in all_games:
            appid = game["appid"]
            name = self._game_name_cache.get(appid)
            if query and not name:
                name = steam_metadata.get_cached_app_name(appid)
                if name:
                    self._game_name_cache[appid] = name
            if not name:
                refs = self._game_card_refs.get(appid)
                if refs:
                    visible_name = refs["name"].cget("text")
                    if visible_name and not visible_name.startswith("App "):
                        name = visible_name
                        self._game_name_cache[appid] = name
            searchable = f"{appid} App {appid} {name or ''}".casefold()
            if not query or query in searchable:
                games.append(game)

        total = len(all_games)
        count = f"{len(games)} of {total}" if query else str(total)
        self.games_count_label.configure(text=f"{count} game{'s' if total != 1 else ''}")
        theme_signature = tuple(sorted(self.active_theme_colors.items()))
        signature = (
            theme_signature,
            self.current_text_color,
            tuple((game["appid"], game["file_path"], game["file_state"]) for game in all_games),
            query,
            tuple(game["appid"] for game in games),
        )
        if signature == self._games_render_signature and self._games_render_index == len(games):
            return
        self._games_render_signature = signature
        if self._games_render_after_id:
            try:
                self.after_cancel(self._games_render_after_id)
            except Exception:
                pass
            self._games_render_after_id = None
        self._games_render_token += 1
        self._games_render_items = games
        self._games_render_index = 0
        for child in self.games_grid.winfo_children():
            child.destroy()
        self._game_card_refs.clear()

        if not games:
            empty = ctk.CTkFrame(self.games_grid, corner_radius=12, fg_color=self._game_surface_color())
            empty.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=8)
            if query and total:
                empty_title = "No matching games"
                empty_text = "Try a different game title or App ID."
            else:
                empty_title = "No games in this folder yet"
                empty_text = "Drop Lua files into the uploader. Files named appid.lua appear here."
            ctk.CTkLabel(empty, text=empty_title, font=(FONT, 14, "bold")).pack(pady=(20, 5))
            ctk.CTkLabel(
                empty, text=empty_text,
                font=(FONT, 11), wraplength=300, justify="center"
            ).pack(padx=16, pady=(0, 18))
            return

        self._render_game_cards_batch(self._games_render_token)

    def _render_game_cards_batch(self, token):
        if token != self._games_render_token:
            return
        start = self._games_render_index
        end = min(start + 16, len(self._games_render_items))
        for index in range(start, end):
            self._create_game_card(index, self._games_render_items[index])
        self._games_render_index = end
        if end < len(self._games_render_items):
            self._games_render_after_id = self.after(
                1, lambda current_token=token: self._render_game_cards_batch(current_token)
            )
        else:
            self._games_render_after_id = None

    def _create_game_card(self, index, game):
        appid = game["appid"]
        card = ctk.CTkFrame(self.games_grid, corner_radius=12, fg_color=self._game_surface_color())
        card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6)
        card.grid_columnconfigure(0, weight=1)
        cover = ctk.CTkLabel(
            card, text="Loading Steam artwork…", width=176, height=82,
            corner_radius=8, fg_color="transparent", font=(FONT, 10)
        )
        cover.pack(fill="x", padx=10, pady=(10, 8))
        name = ctk.CTkLabel(card, text=self._game_name_cache.get(appid, f"App {appid}"), font=(FONT, 12, "bold"),
                            anchor="w", justify="left", wraplength=154, height=34)
        name.pack(fill="x", padx=10)
        id_row = ctk.CTkFrame(card, fg_color="transparent")
        id_row.pack(fill="x", padx=10, pady=(2, 8))
        ctk.CTkLabel(id_row, text="APP ID", font=(FONT, 9, "bold"),
                     text_color="#aebbd0").pack(side="left")
        ctk.CTkLabel(
            id_row, text=appid, font=(FONT, 10, "bold"),
            text_color=config.TEXT_COLORS.get(self.current_text_color, "#ffffff")
        ).pack(side="left", padx=(7, 0))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=8, pady=(0, 10))
        actions.grid_columnconfigure(0, weight=1, uniform="game_actions")
        actions.grid_columnconfigure(1, weight=1, uniform="game_actions")
        ctk.CTkButton(
            actions, text="Folder", width=64, height=29, font=(FONT, 9, "bold"),
            image=self._get_ui_icon("folder-open", "#ffffff", 14), compound="left",
            command=lambda path=game["file_path"]: self.open_lua_location(path)
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(
            actions, text="Remove", width=64, height=29, font=(FONT, 9, "bold"),
            image=self._get_ui_icon("trash-2", "#f87171", 14), compound="left",
            fg_color="transparent", hover_color="#472a32", text_color="#f87171",
            border_width=1, border_color="#713543",
            command=lambda g=game: self.remove_game_card(g)
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self._game_card_refs[appid] = {"name": name, "cover": cover, "file_path": game["file_path"]}
        cached_image = self._game_ctk_images.get(appid)
        if cached_image is not None:
            cover.configure(text="", image=cached_image)
            cover.image = cached_image
        self._queue_game_metadata(appid)

    def _game_surface_color(self):
        colors = getattr(self, "active_theme_colors", config.THEMES.get(self.current_theme, config.THEMES["Dark"]))
        return colors.get("bg", "#121212")

    def _queue_game_metadata(self, appid):
        with self._game_metadata_lock:
            if appid in self._game_metadata_pending:
                return
            self._game_metadata_pending.add(appid)
            if not self._game_workers_started:
                self._game_workers_started = True
                for _ in range(4):
                    threading.Thread(target=self._game_metadata_worker, daemon=True).start()
            self._game_metadata_queue.put(appid)

    def _game_metadata_worker(self):
        while True:
            appid = self._game_metadata_queue.get()
            try:
                self._load_game_metadata(appid)
            except Exception:
                pass
            finally:
                with self._game_metadata_lock:
                    self._game_metadata_pending.discard(appid)
                self._game_metadata_queue.task_done()

    def _load_game_metadata(self, appid):
        os.makedirs(self._game_cover_cache_dir, exist_ok=True)
        metadata = steam_metadata.get_app_metadata(appid)
        title = metadata.get("name") or f"App {appid}"
        cover_url = metadata.get("header_image")
        cover_path = os.path.join(self._game_cover_cache_dir, f"{appid}.jpg")
        thumbnail_path = os.path.join(self._game_cover_cache_dir, f"{appid}_thumb.jpg")

        if cover_url and not os.path.isfile(cover_path):
            try:
                retry_after = float(metadata.get("cover_retry_after", 0) or 0)
            except (TypeError, ValueError):
                retry_after = 0
            if retry_after <= time.time():
                temporary_cover = None
                try:
                    request = urllib.request.Request(
                        cover_url, headers={"User-Agent": "PizzaTools/1.0"}
                    )
                    with urllib.request.urlopen(request, timeout=4) as response:
                        data = response.read()
                    temporary_cover = f"{cover_path}.{threading.get_ident()}.tmp"
                    with open(temporary_cover, "wb") as stream:
                        stream.write(data)
                    os.replace(temporary_cover, cover_path)
                except Exception:
                    metadata["cover_retry_after"] = time.time() + steam_metadata.RETRY_SECONDS
                    steam_metadata.save_app_metadata(appid, metadata)
                    if temporary_cover:
                        try:
                            os.remove(temporary_cover)
                        except OSError:
                            pass

        if os.path.isfile(cover_path) and not os.path.isfile(thumbnail_path):
            temporary_thumbnail = None
            try:
                with Image.open(cover_path) as image:
                    image = ImageOps.fit(image.convert("RGB"), (352, 164), method=Image.LANCZOS)
                    temporary_thumbnail = f"{thumbnail_path}.{threading.get_ident()}.tmp.jpg"
                    image.save(temporary_thumbnail, "JPEG", quality=88, optimize=False)
                os.replace(temporary_thumbnail, thumbnail_path)
            except Exception:
                if temporary_thumbnail:
                    try:
                        os.remove(temporary_thumbnail)
                    except OSError:
                        pass

        display_path = thumbnail_path if os.path.isfile(thumbnail_path) else None
        try:
            self.after(0, lambda: self._show_game_metadata(appid, title, display_path))
        except Exception:
            pass

    def _show_game_metadata(self, appid, title, thumbnail_path):
        previous_name = self._game_name_cache.get(appid, "")
        self._game_name_cache[appid] = title
        query = self._current_game_filter_query
        before = f"{appid} App {appid} {previous_name}".casefold()
        after = f"{appid} App {appid} {title}".casefold()
        if query and (query in before) != (query in after):
            self._schedule_game_search()
        refs = self._game_card_refs.get(appid)
        if not refs:
            return
        refs["name"].configure(text=title)
        if thumbnail_path:
            try:
                cover_image = self._game_ctk_images.get(appid)
                if cover_image is None:
                    with Image.open(thumbnail_path) as image:
                        image = image.convert("RGB")
                        cover_image = ctk.CTkImage(
                            light_image=image.copy(), dark_image=image.copy(), size=(176, 82)
                        )
                    self._game_ctk_images[appid] = cover_image
                refs["cover"].configure(text="", image=cover_image, height=82)
                refs["cover"].image = cover_image
            except Exception:
                refs["cover"].configure(text="Steam artwork unavailable")
                try:
                    os.remove(thumbnail_path)
                except OSError:
                    pass
        else:
            refs["cover"].configure(text="Steam artwork unavailable")

    def open_lua_location(self, file_path):
        if os.path.isfile(file_path):
            subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(file_path)])
        else:
            self.trigger_status_message("Lua file no longer exists.", "File not found")
            self.refresh_games()

    def remove_game_card(self, game):
        file_path = game["file_path"]
        if not os.path.isfile(file_path):
            self.refresh_games()
            return
        if not messagebox.askyesno("Remove game", f"Remove {os.path.basename(file_path)} from your Lua folder?\n\nThis deletes only that Lua file."):
            return
        if Game_remover.remove_lua_file(file_path):
            self.trigger_status_message(f"Removed App {game['appid']}.", "Game removed")
            self.refresh_games()
        else:
            self.trigger_status_message("Couldn't remove the Lua file.", "Remove failed")

    def reset_status(self):
        self.progress_bar.set(0)
        self.status_label.configure(text="Waiting for files...")
        self.reset_timer = None

    def reset_mini_status(self):
        self.mini_status.place_forget()
        self.mini_reset_timer = None

    def trigger_status_message(self, msg, mini_msg, delay_ms=3000):
        if self.is_mini_mode:
            if self.mini_reset_timer:
                self.after_cancel(self.mini_reset_timer)
            self.mini_status.configure(text=mini_msg)
            self.mini_status.place(relx=0.5, rely=0.8, anchor="center")
            self.mini_reset_timer = self.after(delay_ms, self.reset_mini_status)
        else:
            if self.reset_timer:
                self.after_cancel(self.reset_timer)
            self.status_label.configure(text=msg)
            self.reset_timer = self.after(delay_ms, self.reset_status)

    def handle_drop(self, event):
        raw_data = event.data
        if raw_data.startswith('{'):
            files = [f.strip('{}') for f in raw_data.split('} {')]
        else:
            files = raw_data.split()

        total_files = len(files)
        if total_files == 0:
            return

        if self.reset_timer:
            self.after_cancel(self.reset_timer)
        if self.mini_reset_timer:
            self.after_cancel(self.mini_reset_timer)

        if self.is_mini_mode:
            self.mini_status.configure(text="Processing...")
            self.mini_status.place(relx=0.5, rely=0.8, anchor="center")
        else:
            self.progress_bar.set(0)
            self.status_label.configure(text="Processing files...")
        self.update_idletasks()

        threading.Thread(target=self._process_dropped_files, args=(files,), daemon=True).start()

    def _update_drop_progress(self, val, msg, mini_msg="Working..."):
        if self.is_mini_mode:
            self.mini_status.configure(text=mini_msg)
            self.mini_status.place(relx=0.5, rely=0.8, anchor="center")
        else:
            self.progress_bar.set(val)
            self.status_label.configure(text=msg)

    def _show_game_name_dialog(self, archive_name):
        t = config.THEMES.get(self.current_theme, config.THEMES["Dark"])
        txt_col = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")

        dialog = ctk.CTkToplevel(self)
        dialog.geometry("420x280")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.overrideredirect(True)

        dialog.configure(fg_color=t["bg"])

        main_container = ctk.CTkFrame(dialog, fg_color=t["card"], corner_radius=20)
        main_container.pack(fill="both", expand=True, padx=0, pady=0)

        header = ctk.CTkFrame(main_container, fg_color=t["card"], corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)

        title_label = ctk.CTkLabel(
            header,
            text="Game Not Found",
            font=(FONT, 16, "bold"),
            text_color=t["btn"]
        )
        title_label.pack(pady=15)

        header.bind("<Button-1>", lambda e: self._start_dialog_move(e, dialog))
        header.bind("<B1-Motion>", lambda e: self._do_dialog_move(e, dialog))
        title_label.bind("<Button-1>", lambda e: self._start_dialog_move(e, dialog))
        title_label.bind("<B1-Motion>", lambda e: self._do_dialog_move(e, dialog))

        content = ctk.CTkFrame(main_container, fg_color=t["card"])
        content.pack(fill="both", expand=True, padx=20, pady=20)

        info_label = ctk.CTkLabel(
            content,
            text=f"Game not found for: {archive_name}\n\nEnter the game folder name manually:",
            font=(FONT, 12),
            text_color=txt_col,
            wraplength=350
        )
        info_label.pack(pady=(0, 15))

        entry = ctk.CTkEntry(
            content,
            font=(FONT, 12),
            text_color=txt_col,
            fg_color=t["bg"],
            border_color=t["btn"],
            border_width=1,
            placeholder_text="Game folder name or display name",
            height=40,
            corner_radius=10
        )
        entry.pack(pady=10, fill="x", expand=True)
        entry.focus()

        result = {"game_name": None, "confirmed": False}

        def on_ok():
            game_name = entry.get().strip()
            if game_name:
                result["game_name"] = game_name
                result["confirmed"] = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        button_frame = ctk.CTkFrame(content, fg_color="transparent")
        button_frame.pack(pady=(15, 0), fill="x")

        ok_btn = ctk.CTkButton(
            button_frame,
            text="OK",
            font=(FONT, 12, "bold"),
            fg_color=t["btn"],
            hover_color=t["btn_hover"],
            text_color=txt_col,
            command=on_ok,
            corner_radius=10,
            height=38
        )
        ok_btn.pack(side="left", fill="both", expand=True, padx=(0, 8))

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            font=(FONT, 12, "bold"),
            fg_color=t["bg"],
            hover_color=t["btn"],
            text_color=txt_col,
            border_width=1,
            border_color=t["btn"],
            command=on_cancel,
            corner_radius=10,
            height=38
        )
        cancel_btn.pack(side="left", fill="both", expand=True)

        entry.bind("<Return>", lambda e: on_ok())

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        self._dialog_x = 0
        self._dialog_y = 0

        dialog.wait_window()

        return result

    def _start_dialog_move(self, event, dialog):
        self._dialog_x = event.x_root - dialog.winfo_x()
        self._dialog_y = event.y_root - dialog.winfo_y()

    def _do_dialog_move(self, event, dialog):
        x = event.x_root - self._dialog_x
        y = event.y_root - self._dialog_y
        dialog.geometry(f"+{x}+{y}")

    def _process_dropped_files(self, files):
        total_files = len(files)
        results = []
        installed_games_cache = None

        for i, file_path in enumerate(files):
            file_path = file_path.strip('"')
            if not os.path.exists(file_path):
                continue

            lower_path = file_path.lower()
            filename = os.path.basename(os.path.normpath(file_path))

            progress_val = (i + 0.3) / total_files
            self.after(0, lambda pv=progress_val, fn=filename: self._update_drop_progress(pv, f"Processing {fn}...", "Working..."))

            if os.path.isdir(file_path):
                self.after(0, lambda pv=progress_val, fn=filename: self._update_drop_progress(pv, f"Patching {fn}...", "Patching..."))
                if installed_games_cache is None:
                    self.steam_path = self._ensure_steam_path()
                    installed_games_cache = onlinefix_utils.get_installed_steam_games(self.steam_path)

                res = onlinefix_utils.process_onlinefix_folder(
                    file_path,
                    self.steam_path,
                    games_cache=installed_games_cache
                )
                if res["status"] == "success":
                    if not res["errors"]:
                        results.append(("game_success", (res["game_name"], res["copied_count"])))
                    else:
                        results.append(("game_partial", (res["game_name"], res["copied_count"], len(res["errors"]))))
                elif res["status"] == "game_not_found":
                    dialog_result = self._show_game_name_dialog(filename)

                    if dialog_result["confirmed"] and dialog_result["game_name"]:
                        game_name = dialog_result["game_name"]
                        game_match, score = onlinefix_utils.find_matching_game(game_name, installed_games_cache)

                        if game_match and score >= 0.70:
                            game_dir = game_match["path"]
                            payload_dir = onlinefix_utils.resolve_payload_source_dir(
                                file_path,
                                target_game_path=game_dir,
                                target_game_folder_name=game_match.get("folder_name"),
                                target_game_display_name=game_match.get("display_name")
                            )
                            copied_count, errors = onlinefix_utils.apply_game_fix(payload_dir, game_dir)
                            game_title = game_match.get("display_name") or game_match.get("folder_name", "Game")
                            if not errors:
                                results.append(("game_success", (game_title, copied_count)))
                            else:
                                results.append(("game_partial", (game_title, copied_count, len(errors))))
                        else:
                            lua_copied = 0
                            try:
                                if not file_utils.ensure_target_directory(self.target_dir):
                                    results.append(("error", "Failed to create target directory"))
                                else:
                                    for root, _dirs, fnames in os.walk(file_path):
                                        for fn in fnames:
                                            if fn.lower().endswith(".lua"):
                                                dest = os.path.join(self.target_dir, fn)
                                                shutil.copy2(os.path.join(root, fn), dest)
                                                lua_copied += 1
                            except Exception:
                                pass

                            if lua_copied > 0:
                                results.append(("lua_success", f"{lua_copied} Lua file(s)"))
                            else:
                                results.append(("game_not_found", filename))
                    else:
                        lua_copied = 0
                        try:
                            if not file_utils.ensure_target_directory(self.target_dir):
                                results.append(("error", "Failed to create target directory"))
                            else:
                                for root, _dirs, fnames in os.walk(file_path):
                                    for fn in fnames:
                                        if fn.lower().endswith(".lua"):
                                            dest = os.path.join(self.target_dir, fn)
                                            shutil.copy2(os.path.join(root, fn), dest)
                                            lua_copied += 1
                        except Exception:
                            pass

                        if lua_copied > 0:
                            results.append(("lua_success", f"{lua_copied} Lua file(s)"))
                        else:
                            results.append(("game_not_found", filename))
                else:
                    results.append(("error", res.get("error_msg") or f"Error in {filename}"))

            elif lower_path.endswith('.lua'):
                try:
                    if not file_utils.ensure_target_directory(self.target_dir):
                        results.append(("error", f"Failed to create target directory for {filename}"))
                        continue

                    destination = os.path.join(self.target_dir, filename)
                    shutil.copy2(file_path, destination)

                    base_name = os.path.splitext(filename)[0]
                    game_name = steam_metadata.get_app_name(base_name) if base_name.isdigit() else None

                    if game_name:
                        results.append(("lua_success_named", (filename, game_name)))
                    else:
                        results.append(("lua_success", filename))
                except Exception:
                    results.append(("error", f"Failed to copy {filename}"))

            elif lower_path.endswith('.manifest'):
                try:
                    steam_path = self._ensure_steam_path()
                    ok, result = manifest_utils.install_manifest_file(file_path, steam_path=steam_path)
                    if ok:
                        results.append(("manifest_success", filename))
                    else:
                        results.append(("error", f"{filename}: {result}"))
                except Exception as e:
                    results.append(("error", f"{filename}: {e}"))

            elif lower_path.endswith(('.rar', '.7z', '.tar', '.gz', '.tgz', '.tar.gz')):
                self.after(0, lambda pv=progress_val, fn=filename: self._update_drop_progress(pv, f"Patching {fn}...", "Patching..."))
                if installed_games_cache is None:
                    self.steam_path = self._ensure_steam_path()
                    installed_games_cache = onlinefix_utils.get_installed_steam_games(self.steam_path)

                pwd = getattr(config, "ONLINE_FIX_PASSWORD", "online-fix.me")
                res = onlinefix_utils.process_onlinefix_archive(
                    file_path,
                    self.steam_path,
                    password=pwd,
                    games_cache=installed_games_cache
                )
                if res["status"] == "success":
                    if self.settings.get("delete_rar_after_patch", False) and lower_path.endswith('.rar'):
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                    if not res["errors"]:
                        results.append(("game_success", (res["game_name"], res["copied_count"])))
                    else:
                        results.append(("game_partial", (res["game_name"], res["copied_count"], len(res["errors"]))))
                elif res["status"] == "game_not_found":
                    if lower_path.endswith('.rar'):
                        dialog_result = self._show_game_name_dialog(filename)

                        if dialog_result["confirmed"] and dialog_result["game_name"]:
                            game_name = dialog_result["game_name"]
                            game_match, score = onlinefix_utils.find_matching_game(game_name, installed_games_cache)

                            if game_match and score >= 0.70:
                                import tempfile
                                temp_dir = tempfile.mkdtemp(prefix="pizza_fix_")
                                try:
                                    success, err = onlinefix_utils.extract_rar_archive(file_path, temp_dir, password=pwd)
                                    if success:
                                        game_dir = game_match["path"]
                                        payload_dir = onlinefix_utils.resolve_payload_source_dir(
                                            temp_dir,
                                            target_game_path=game_dir,
                                            target_game_folder_name=game_match.get("folder_name"),
                                            target_game_display_name=game_match.get("display_name")
                                        )
                                        copied_count, errors = onlinefix_utils.apply_game_fix(payload_dir, game_dir)
                                        game_title = game_match.get("display_name") or game_match.get("folder_name", "Game")

                                        if self.settings.get("delete_rar_after_patch", False):
                                            try:
                                                os.remove(file_path)
                                            except Exception:
                                                pass

                                        if not errors:
                                            results.append(("game_success", (game_title, copied_count)))
                                        else:
                                            results.append(("game_partial", (game_title, copied_count, len(errors))))
                                    else:
                                        results.append(("error", f"Failed to extract {filename}"))
                                finally:
                                    shutil.rmtree(temp_dir, ignore_errors=True)
                            else:
                                results.append(("game_not_found", filename))
                        else:
                            results.append(("game_not_found", filename))
                    else:
                        results.append(("game_not_found", filename))
                else:
                    results.append(("error", res.get("error_msg") or f"Error patching {filename}"))

            elif lower_path.endswith('.zip'):
                manifests_installed = 0
                manifests_errors = []
                if manifest_utils.has_manifests(file_path):
                    self.after(0, lambda pv=progress_val, fn=filename:
                               self._update_drop_progress(pv, f"Installing manifests from {fn}...", "Manifests..."))
                    steam_path = self._ensure_steam_path()
                    entries = manifest_utils.extract_manifests_only(file_path)
                    depotcache = None
                    if steam_path:
                        depotcache = os.path.join(steam_path, "depotcache")
                        try:
                            os.makedirs(depotcache, exist_ok=True)
                        except Exception:
                            depotcache = None

                    if depotcache:
                        for name, data in entries:
                            try:
                                dest = os.path.join(depotcache, name)
                                with open(dest, "wb") as f:
                                    f.write(data)
                                manifests_installed += 1
                            except Exception as e:
                                manifests_errors.append(f"{name}: {e}")
                    else:
                        manifests_errors.append("Steam/depotcache not found")

                    if manifests_installed > 0:
                        results.append(("manifest_zip_success", manifests_installed))
                    if manifests_errors:
                        results.append(("manifest_zip_partial", (manifests_installed, len(manifests_errors))))

                if manifest_utils.is_manifest_only_zip(file_path):
                    if self.settings.get("delete_zip_after_extract", False) and manifests_installed > 0:
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                    continue

                is_pure_lua = False
                try:
                    with zipfile.ZipFile(file_path, "r") as z:
                        namelist = [n.lower() for n in z.namelist() if not n.endswith('/')]
                        lua_files = [n for n in namelist if n.endswith('.lua')]
                        game_files = [n for n in namelist if n.endswith(('.dll', '.exe', '.ini', '.pak', '.bin', '.dat'))]
                        if lua_files and not game_files:
                            is_pure_lua = True
                except Exception:
                    pass

                if is_pure_lua:
                    extracted_lua, zip_errors, zip_game_names = archive_utils.extract_lua_files_from_zip(
                        file_path, self.target_dir
                    )
                    if extracted_lua > 0:
                        if zip_game_names:
                            results.append(("lua_zip_success_named", (extracted_lua, zip_game_names)))
                        else:
                            results.append(("lua_zip_success", extracted_lua))
                        if self.settings.get("delete_zip_after_extract", False):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                    else:
                        results.append(("error", f"Failed to extract Lua from {filename}"))
                else:
                    self.after(0, lambda pv=progress_val, fn=filename:
                               self._update_drop_progress(pv, f"Patching {fn}...", "Patching..."))
                    if installed_games_cache is None:
                        self.steam_path = self._ensure_steam_path()
                        installed_games_cache = onlinefix_utils.get_installed_steam_games(self.steam_path)

                    pwd = getattr(config, "ONLINE_FIX_PASSWORD", "online-fix.me")
                    res = onlinefix_utils.process_onlinefix_archive(
                        file_path,
                        self.steam_path,
                        password=pwd,
                        games_cache=installed_games_cache
                    )
                    if res["status"] == "success":
                        if self.settings.get("delete_zip_after_extract", False):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                        if not res["errors"]:
                            results.append(("game_success", (res["game_name"], res["copied_count"])))
                        else:
                            results.append(("game_partial", (res["game_name"], res["copied_count"], len(res["errors"]))))
                    elif res["status"] == "game_not_found":
                        extracted_lua, _, zip_game_names = archive_utils.extract_lua_files_from_zip(file_path, self.target_dir)
                        if extracted_lua > 0:
                            if zip_game_names:
                                results.append(("lua_zip_success_named", (extracted_lua, zip_game_names)))
                            else:
                                results.append(("lua_zip_success", extracted_lua))
                        else:
                            results.append(("game_not_found", filename))
                    else:
                        results.append(("error", res.get("error_msg") or f"Error in {filename}"))
            else:
                results.append(("ignored", filename))

            self.after(0, lambda pv=(i + 1) / total_files: self._update_drop_progress(pv, "Finishing..."))

        self.after(0, lambda: self._finalize_drop_results(results))

    def _finalize_drop_results(self, results):
        if self.current_view == "games":
            self.refresh_games()
        lua_count = 0
        lua_named_games = []
        manifest_count = 0
        games_patched = []
        games_partial = []
        games_not_found = []
        errors = []
        ignored_count = 0

        for rtype, rdata in results:
            if rtype == "lua_success":
                lua_count += 1
            elif rtype == "lua_success_named":
                lua_count += 1
                lua_named_games.append(rdata)
            elif rtype == "lua_zip_success":
                lua_count += rdata
            elif rtype == "lua_zip_success_named":
                count, names = rdata
                lua_count += count
                for name in names:
                    lua_named_games.append((None, name))
            elif rtype == "manifest_success":
                manifest_count += 1
            elif rtype == "manifest_zip_success":
                manifest_count += rdata
            elif rtype == "manifest_zip_partial":
                copied_m, err_m = rdata
                manifest_count += copied_m
                errors.append(f"Manifests: {err_m} warning(s)")
            elif rtype == "game_success":
                games_patched.append(rdata)
            elif rtype == "game_partial":
                games_partial.append(rdata)
            elif rtype == "game_not_found":
                games_not_found.append(rdata)
            elif rtype == "error":
                errors.append(rdata)
            elif rtype == "ignored":
                ignored_count += 1

        if manifest_count > 0 and not games_patched and not games_partial and not errors \
                and not games_not_found and lua_count == 0:
            msg = f"Successfully installed {manifest_count} manifest file(s) to depotcache!"
            mini_msg = f"{manifest_count} manifests!"
        elif games_patched and not games_partial and not errors and not games_not_found and lua_count == 0 and manifest_count == 0:
            if len(games_patched) == 1:
                gname, cnt = games_patched[0]
                msg = f"Successfully patched '{gname}' ({cnt} file(s) overwritten)!"
                mini_msg = f"{gname} patched!"
            else:
                names = ", ".join(g[0] for g in games_patched)
                msg = f"Patched {len(games_patched)} games ({names})!"
                mini_msg = f"{len(games_patched)} patched!"
        elif games_partial and not games_patched and not errors and not games_not_found and lua_count == 0 and manifest_count == 0:
            gname, cnt, err_cnt = games_partial[0]
            msg = f"Patched '{gname}' with {err_cnt} warning(s) ({cnt} file(s) copied)."
            mini_msg = f"{gname} patched (warn)!"
        elif lua_count > 0 and not games_patched and not games_partial and not errors and not games_not_found and manifest_count == 0:
            if len(lua_named_games) == 1:
                _, gname = lua_named_games[0]
                msg = f"Successfully uploaded '{gname}' Lua file!"
                mini_msg = f"{gname} added!"
            elif len(lua_named_games) > 1:
                names = ", ".join(g[1] for g in lua_named_games)
                msg = f"Uploaded {lua_count} Lua files ({names})!"
                mini_msg = f"{len(lua_named_games)} added!"
            else:
                msg = f"Successfully uploaded {lua_count} Lua file(s)!"
                mini_msg = f"{lua_count} added!"
        elif games_not_found and not games_patched and not games_partial and lua_count == 0 and not errors and manifest_count == 0:
            clean_name = onlinefix_utils.clean_archive_name(games_not_found[0])
            msg = f"Game '{clean_name}' not found in Steam libraries."
            mini_msg = "Game not found!"
        else:
            parts = []
            if games_patched:
                parts.append(f"Patched: {', '.join(g[0] for g in games_patched)}")
            if games_partial:
                parts.append(f"Partial: {', '.join(g[0] for g in games_partial)}")
            if lua_count > 0:
                parts.append(f"Lua: {lua_count}")
            if manifest_count > 0:
                parts.append(f"Manifests: {manifest_count}")
            if games_not_found:
                parts.append(f"Not found: {len(games_not_found)}")
            if errors:
                parts.append(f"Errors: {len(errors)}")
            if ignored_count > 0:
                parts.append(f"Skipped: {ignored_count}")
            msg = " | ".join(parts) if parts else "Done."
            mini_msg = "Finished!"

        self.trigger_status_message(msg, mini_msg, delay_ms=4500)

    def _run_update_check(self):
        """Automatischer Check beim Start – kein Dialog wenn aktuell (silent=True)."""
        t   = config.THEMES.get(self.current_theme, config.THEMES["Dark"])
        txt = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")
        updater.check_for_update(self, theme=t, text_color=txt, silent=True)

    def manual_update_check(self):
        """Manuell per Button ausgelöst – zeigt auch 'Du bist aktuell' (silent=False)."""
        t   = config.THEMES.get(self.current_theme, config.THEMES["Dark"])
        txt = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")
        updater.check_for_update(self, theme=t, text_color=txt, silent=False)

    def toggle_autostart(self):
        enable = self.autostart_switch.get() == 1
        success = windows_integration.set_autostart(config.REG_APP_NAME, enable)
        if success:
            if enable:
                self.trigger_status_message("Autostart enabled.", "On")
            else:
                self.trigger_status_message("Autostart disabled.", "Off")
        else:
            self.trigger_status_message("Failed to update autostart.", "Error")

    def create_desktop_shortcut(self):
        success = windows_integration.create_desktop_shortcut()
        if success:
            self.trigger_status_message("Desktop shortcut created!", "Shortcut created")
        else:
            self.trigger_status_message("Failed to create shortcut.", "Error")


import os
import shutil
import webbrowser
import threading
import ctypes
import tempfile
import zipfile

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk

from . import config
from . import image_utils
from . import windows_integration
from . import archive_utils
from . import steam_utils
from . import onlinefix_utils
from . import patch_utils
from . import Game_remover
from . import manifest_utils
from .discord_rpc import DiscordRPC

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

        self.title("Pizza Tools by pizzathegoat , Daniel_99")

        self.ctk_ctx = ctk.CTk()
        self.ctk_ctx.withdraw()

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

        self.reset_timer = None
        self.mini_reset_timer = None
        self.is_mini_mode = False
        self.tray_icon = None
        self._mini_size = config.MINI_LOGO_SIZE[0] * 3
        self.discord = DiscordRPC(config.DISCORD_RPC_CLIENT_ID)

        self.load_config()
        self.load_images()
        self.init_ui()
        self.apply_theme(self.current_theme)

        self.after(50, self.apply_theme)
        self.after(200, self.apply_theme)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.settings.get("discord_rpc", False):
            threading.Thread(target=self.start_discord_rpc, daemon=True).start()

        self.after(3000, self._poll_steam_status)

    def load_config(self):
        self.settings = config.load_settings()

        self.current_theme = self.settings.get("theme", "Dark")
        self.current_text_color = self.settings.get("text_color", "White")
        self.target_dir = self.settings.get("target_dir", r"C:\Program Files (x86)\Steam\config\Lua")

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
            self.img_logo = ctk.CTkImage(light_image=logo_data, dark_image=logo_data, size=(80, 80))

            theme = config.THEMES.get(self.current_theme, config.THEMES["Dark"])
            glow_rgb = _hex_to_rgb(theme.get("btn", "#2b2b2b"))

            mini_logo_clean = image_utils.prepare_mini_logo(logo_data, config.MINI_LOGO_SIZE)
            glow_img = image_utils.make_glow_logo(
                mini_logo_clean,
                config.MINI_LOGO_SIZE,
                glow_color=glow_rgb,
                intensity=1.15,
            )
            self._mini_size = glow_img.size[0]
            self.img_logo_mini = ctk.CTkImage(
                light_image=glow_img, dark_image=glow_img,
                size=glow_img.size
            )
            self._mini_glow_base = mini_logo_clean
        except Exception:
            pass

        try:
            ico_path = config.APP_ICON
            if os.path.exists(ico_path):
                self.iconbitmap(default=ico_path)
                taskbar_data = Image.open(ico_path).convert("RGBA")
            else:
                taskbar_data = image_utils.load_pil_image(config.LOGO_FILENAME)

            icon_img = ImageTk.PhotoImage(taskbar_data)
            self.iconphoto(True, icon_img)
            self.tray_pil_image = taskbar_data.resize(config.TRAY_ICON_SIZE, Image.LANCZOS)
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

        self.toggle_btn = ctk.CTkButton(
            self.header_zone, text=" Settings", image=self.icon_settings,
            width=100, font=(FONT, 12, "bold"), command=self.switch_view
        )
        self.toggle_btn.pack(side="right", padx=15)

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

        self.settings_view = ctk.CTkScrollableFrame(self.content_container, corner_radius=12)

        self.theme_label = ctk.CTkLabel(self.settings_view, text="Theme Color", font=(FONT, 13, "bold"))
        self.theme_label.pack(anchor="w", padx=25, pady=(15, 5))
        self.theme_menu = ctk.CTkOptionMenu(self.settings_view, values=list(config.THEMES.keys()),
                                            command=self.change_theme,
                                            font=(FONT, 12, "bold"), width=200,
                                            corner_radius=SMALL_CORNER, height=32)
        self.theme_menu.pack(anchor="w", padx=25, pady=(0, 10))
        self.theme_menu.set(self.current_theme)

        self.text_label = ctk.CTkLabel(self.settings_view, text="Text Color", font=(FONT, 13, "bold"))
        self.text_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.text_menu = ctk.CTkOptionMenu(self.settings_view, values=list(config.TEXT_COLORS.keys()),
                                           command=self.change_text_color, font=(FONT, 12, "bold"), width=200,
                                           corner_radius=SMALL_CORNER, height=32)
        self.text_menu.pack(anchor="w", padx=25, pady=(0, 10))
        self.text_menu.set(self.current_text_color)

        self.path_label = ctk.CTkLabel(self.settings_view, text="Save Folder", font=(FONT, 13, "bold"))
        self.path_label.pack(anchor="w", padx=25, pady=(5, 5))

        path_frame = ctk.CTkFrame(self.settings_view, fg_color="transparent")
        path_frame.pack(fill="x", padx=25, pady=(0, 10))
        self.path_entry = ctk.CTkEntry(path_frame, font=(FONT, 11), corner_radius=SMALL_CORNER, height=32)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.path_entry.insert(0, self.target_dir)
        self.path_entry.configure(state="disabled")

        self.path_btn = ctk.CTkButton(path_frame, text="Browse", width=60, font=(FONT, 11, "bold"),
                                      corner_radius=SMALL_CORNER, command=self.browse_path)
        self.path_btn.pack(side="right")

        self.remove_game_label = ctk.CTkLabel(self.settings_view, text="Remove Game (by Game ID)",
                                              font=(FONT, 13, "bold"))
        self.remove_game_label.pack(anchor="w", padx=25, pady=(5, 5))

        remove_game_frame = ctk.CTkFrame(self.settings_view, fg_color="transparent")
        remove_game_frame.pack(fill="x", padx=25, pady=(0, 10))
        self.remove_game_entry = ctk.CTkEntry(remove_game_frame, font=(FONT, 11), placeholder_text="Game ID, e.g. 67",
                                              corner_radius=SMALL_CORNER, height=32)
        self.remove_game_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.remove_game_entry.bind("<Return>", lambda event: self.remove_game())

        self.remove_game_btn = ctk.CTkButton(remove_game_frame, text="Remove", width=60,
                                             font=(FONT, 11, "bold"), corner_radius=SMALL_CORNER,
                                             command=self.remove_game)
        self.remove_game_btn.pack(side="right")

        self.autostart_label = ctk.CTkLabel(self.settings_view, text="System Startup", font=(FONT, 13, "bold"))
        self.autostart_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.autostart_switch = ctk.CTkSwitch(self.settings_view, text="Launch app on PC startup", font=(FONT, 12),
                                              command=self.toggle_autostart)
        self.autostart_switch.pack(anchor="w", padx=25, pady=(0, 10))

        if windows_integration.is_autostart_enabled(config.REG_APP_NAME):
            self.autostart_switch.select()

        self.discord_rpc_label = ctk.CTkLabel(self.settings_view, text="Discord Rich Presence",
                                              font=(FONT, 13, "bold"))
        self.discord_rpc_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.discord_rpc_switch = ctk.CTkSwitch(self.settings_view, text="Show activity on Discord profile",
                                                font=(FONT, 12), command=self.toggle_discord_rpc)
        self.discord_rpc_switch.pack(anchor="w", padx=25, pady=(0, 25))

        if self.settings.get("discord_rpc", False):
            self.discord_rpc_switch.select()

        self.zip_cleanup_label = ctk.CTkLabel(self.settings_view, text="ZIP Cleanup",
                                              font=(FONT, 13, "bold"))
        self.zip_cleanup_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.zip_cleanup_switch = ctk.CTkSwitch(self.settings_view,
                                                text="Delete ZIP after successful extraction",
                                                font=(FONT, 12), command=self.toggle_delete_zip_after_extract)
        self.zip_cleanup_switch.pack(anchor="w", padx=25, pady=(0, 25))

        if self.settings.get("delete_zip_after_extract", False):
            self.zip_cleanup_switch.select()

        self.steam_patch_label = ctk.CTkLabel(self.settings_view, text="OpenSteamTools Patch",
                                              font=(FONT, 13, "bold"))
        self.steam_patch_label.pack(anchor="w", padx=25, pady=(5, 5))
        self.steam_patch_btn = ctk.CTkButton(self.settings_view, text="Apply Patch",
                                             font=(FONT, 12, "bold"), command=self.apply_steam_patch)
        self.steam_patch_btn.pack(anchor="w", padx=25, pady=(0, 10))

        self.steam_control_label = ctk.CTkLabel(self.settings_view, text="Steam Control",
                                                font=(FONT, 13, "bold"))
        self.steam_control_label.pack(anchor="w", padx=25, pady=(5, 5))

        steam_control_frame = ctk.CTkFrame(self.settings_view, fg_color="transparent")
        steam_control_frame.pack(fill="x", padx=25, pady=(0, 25))

        self.steam_action_btn = ctk.CTkButton(steam_control_frame, text=self._steam_action_label_text(),
                                              font=(FONT, 12, "bold"), command=self.handle_steam_action)
        self.steam_action_btn.pack(side="left", padx=(0, 10))

        self.steam_close_btn = ctk.CTkButton(steam_control_frame, text="Close Steam",
                                             font=(FONT, 12, "bold"), command=self.handle_close_steam)
        self.steam_close_btn.pack(side="left")

        self.mini_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=config.TRANSPARENT_KEY,
                                       border_width=0)

        mini_logo_image = self.img_logo_mini if self.img_logo_mini else self.img_logo
        if mini_logo_image:
            self.mini_logo = ctk.CTkLabel(self.mini_frame, image=mini_logo_image, text="",
                                          fg_color=config.TRANSPARENT_KEY)
        else:
            self.mini_logo = ctk.CTkLabel(self.mini_frame, text="[Logo]", font=(FONT, 16, "bold"),
                                          fg_color=config.TRANSPARENT_KEY)
        self.mini_logo.place(relx=0.5, rely=0.5, anchor="center")

        self.mini_status = ctk.CTkLabel(self.mini_frame, text="", font=(FONT, 11, "bold"),
                                        corner_radius=6, text_color="#ffffff")

        self.mini_logo.bind("<Double-Button-1>", self.toggle_mini_mode)
        self.mini_frame.bind("<Double-Button-1>", self.toggle_mini_mode)

        self.mini_logo.bind("<Button-3>", self.show_mini_context_menu)
        self.mini_frame.bind("<Button-3>", self.show_mini_context_menu)

        self.mini_logo.bind("<ButtonPress-1>", self.start_move)
        self.mini_logo.bind("<B1-Motion>", self.do_move)
        self.mini_frame.bind("<ButtonPress-1>", self.start_move)
        self.mini_frame.bind("<B1-Motion>", self.do_move)

        self.uploader_view.drop_target_register(DND_FILES)
        self.uploader_view.dnd_bind('<<Drop>>', self.handle_drop)

        self.mini_frame.drop_target_register(DND_FILES)
        self.mini_frame.dnd_bind('<<Drop>>', self.handle_drop)

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

            h_icon_big = ctypes.windll.user32.LoadImageW(
                None, ico_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
            h_icon_small = ctypes.windll.user32.LoadImageW(
                None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
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
        self.close_context_menu()

        self.withdraw()

        if not self.is_mini_mode:
            self.is_mini_mode = True
            self.main_frame.pack_forget()

            self.overrideredirect(True)
            self.attributes("-topmost", True)

            x = self.winfo_x() + 150
            y = self.winfo_y() + 200
            size = self._mini_size
            self.geometry(f"{size}x{size}+{x}+{y}")

            self.configure(bg=config.TRANSPARENT_KEY)
            try:
                self.attributes("-transparentcolor", config.TRANSPARENT_KEY)
            except Exception:
                pass

            self.mini_frame.pack(fill="both", expand=True)
        else:
            self.is_mini_mode = False
            self.mini_frame.pack_forget()

            try:
                self.attributes("-transparentcolor", "")
            except Exception:
                pass

            self.overrideredirect(False)
            self.attributes("-topmost", False)

            x = self.winfo_x() - 150
            y = self.winfo_y() - 200
            self.geometry(f"450x700+{x}+{y}")

            self.main_frame.pack(fill="both", expand=True)
            self.apply_theme()

        self.update_idletasks()
        self.deiconify()

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
            "Apply OpenSteamTools Patch",
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
        try:
            self.refresh_steam_action_button()
        except Exception:
            pass

        try:
            self.after(3000, self._poll_steam_status)
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

    def apply_theme(self, theme_name=None):
        if theme_name: self.current_theme = theme_name
        t = config.THEMES.get(self.current_theme, config.THEMES["Dark"])
        txt_col = config.TEXT_COLORS.get(self.current_text_color, "#ffffff")

        self.set_title_bar_color(t["bg"])

        self.mini_status.configure(fg_color=t["card"])

        self.main_frame.configure(fg_color=t["bg"])
        self.header_zone.configure(fg_color=t["card"])
        self.uploader_view.configure(fg_color=t["card"])
        self.settings_view.configure(fg_color=t["card"])

        self.progress_bar.configure(progress_color=t["btn"], fg_color=t["card"])
        self.status_label.configure(text_color=txt_col)
        self.title_label.configure(text_color=txt_col)
        self.drop_label.configure(text_color=txt_col)
        self.theme_label.configure(text_color=txt_col)
        self.text_label.configure(text_color=txt_col)
        self.path_label.configure(text_color=txt_col)
        self.remove_game_label.configure(text_color=txt_col)
        self.autostart_label.configure(text_color=txt_col)
        self.discord_rpc_label.configure(text_color=txt_col)
        self.zip_cleanup_label.configure(text_color=txt_col)
        self.steam_patch_label.configure(text_color=txt_col)
        self.steam_control_label.configure(text_color=txt_col)
        self.path_entry.configure(text_color=txt_col, fg_color=t["bg"], border_color=t["accent"])
        self.remove_game_entry.configure(text_color=txt_col, fg_color=t["bg"], border_color=t["accent"])
        self.autostart_switch.configure(text_color=txt_col, progress_color=t["btn"])
        self.discord_rpc_switch.configure(text_color=txt_col, progress_color=t["btn"])
        self.zip_cleanup_switch.configure(text_color=txt_col, progress_color=t["btn"])

        self.toggle_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
        self.path_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
        self.remove_game_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
        self.steam_patch_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
        self.steam_action_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)
        self.steam_close_btn.configure(fg_color=t["btn"], hover_color=t["btn_hover"], text_color=txt_col)

        self.theme_menu.configure(fg_color=t["btn"], button_color=t["btn"], button_hover_color=t["btn_hover"],
                                  text_color=txt_col, dropdown_fg_color=t["card"], dropdown_hover_color=t["btn_hover"],
                                  dropdown_text_color=txt_col)
        self.text_menu.configure(fg_color=t["btn"], button_color=t["btn"], button_hover_color=t["btn_hover"],
                                 text_color=txt_col, dropdown_fg_color=t["card"], dropdown_hover_color=t["btn_hover"],
                                 dropdown_text_color=txt_col)

        self._rebuild_mini_glow()

    def _rebuild_mini_glow(self):
        base = getattr(self, "_mini_glow_base", None)
        if base is None:
            return
        theme = config.THEMES.get(self.current_theme, config.THEMES["Dark"])
        glow_rgb = _hex_to_rgb(theme.get("btn", "#2b2b2b"))
        try:
            glow_img = image_utils.make_glow_logo(
                base, config.MINI_LOGO_SIZE,
                glow_color=glow_rgb, intensity=1.15,
            )
            self._mini_size = glow_img.size[0]
            self.img_logo_mini = ctk.CTkImage(
                light_image=glow_img, dark_image=glow_img,
                size=glow_img.size
            )
            if hasattr(self, "mini_logo"):
                self.mini_logo.configure(image=self.img_logo_mini)
        except Exception:
            pass

    def open_discord(self):
        webbrowser.open(config.DISCORD_LINK)

    def switch_view(self):
        if self.current_view == "uploader":
            self.uploader_view.pack_forget()
            self.settings_view.pack(fill="both", expand=True, padx=20, pady=(0, 15))
            self.toggle_btn.configure(text=" Back", image=self.icon_back)
            self.current_view = "settings"
            self.refresh_steam_action_button()
        else:
            self.settings_view.pack_forget()
            self.uploader_view.pack(fill="both", expand=True, padx=20, pady=(0, 15))
            self.toggle_btn.configure(text=" Settings", image=self.icon_settings)
            self.current_view = "uploader"

    def reset_status(self):
        self.progress_bar.set(0)
        self.status_label.configure(text="Waiting for files...")
        self.reset_timer = None

    def reset_mini_status(self):
        self.mini_status.place_forget()
        self.mini_reset_timer = None

    def trigger_status_message(self, msg, mini_msg, delay_ms=3000):
        if self.is_mini_mode:
            if self.mini_reset_timer: self.after_cancel(self.mini_reset_timer)
            self.mini_status.configure(text=mini_msg)
            self.mini_status.place(relx=0.5, rely=0.9, anchor="center")
            self.mini_reset_timer = self.after(delay_ms, self.reset_mini_status)
        else:
            if self.reset_timer: self.after_cancel(self.reset_timer)
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
            self.mini_status.place(relx=0.5, rely=0.9, anchor="center")
        else:
            self.progress_bar.set(0)
            self.status_label.configure(text="Processing files...")
        self.update_idletasks()

        threading.Thread(target=self._process_dropped_files, args=(files,), daemon=True).start()

    def _update_drop_progress(self, val, msg, mini_msg="Working..."):
        if self.is_mini_mode:
            self.mini_status.configure(text=mini_msg)
            self.mini_status.place(relx=0.5, rely=0.9, anchor="center")
        else:
            self.progress_bar.set(val)
            self.status_label.configure(text=msg)

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
                    lua_copied = 0
                    try:
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
                    destination = os.path.join(self.target_dir, filename)
                    shutil.copy2(file_path, destination)
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
                    if not res["errors"]:
                        results.append(("game_success", (res["game_name"], res["copied_count"])))
                    else:
                        results.append(("game_partial", (res["game_name"], res["copied_count"], len(res["errors"]))))
                elif res["status"] == "game_not_found":
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
                    extracted_lua, zip_errors = archive_utils.extract_lua_files_from_zip(
                        file_path, self.target_dir
                    )
                    if extracted_lua > 0:
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
                        extracted_lua, _ = archive_utils.extract_lua_files_from_zip(file_path, self.target_dir)
                        if extracted_lua > 0:
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
        lua_count = 0
        manifest_count = 0
        games_patched = []
        games_partial = []
        games_not_found = []
        errors = []
        ignored_count = 0

        for rtype, rdata in results:
            if rtype == "lua_success":
                lua_count += 1
            elif rtype == "lua_zip_success":
                lua_count += rdata
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
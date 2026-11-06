import os
import sys
import winreg
import ctypes

try:
    import pystray
except ImportError:
    pystray = None


def get_app_command():
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    parent_dir = os.path.dirname(base_dir)  
    

    main_pyw_path = os.path.join(parent_dir, "main.pyw")
    
    if os.path.isfile(main_pyw_path):
        script_path = main_pyw_path
    else:
        script_path = os.path.abspath(sys.argv[0])

    return f'"{script_path}"'


def is_autostart_enabled(app_name):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_autostart(app_name, enable):
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_cmd = get_app_command()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def set_title_bar_color(window, hex_color="#121212"):
    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi

        hwnd = user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = user32.GetAncestor(window.winfo_id(), 2)
        if not hwnd:
            hwnd = window.winfo_id()

        dark_value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_value), ctypes.sizeof(dark_value))
        dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_value), ctypes.sizeof(dark_value))

        if hex_color:
            hex_str = hex_color.lstrip('#')
            r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
            color_ref = ctypes.c_int(b << 16 | g << 8 | r)
            dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color_ref), ctypes.sizeof(color_ref))
            white_ref = ctypes.c_int(0x00FFFFFF)
            dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(white_ref), ctypes.sizeof(white_ref))
    except Exception:
        pass



def create_tray_icon(image, on_show, on_quit):
    if pystray is None:
        return None
    menu = pystray.Menu(
        pystray.MenuItem("Show", on_show, default=True),
        pystray.MenuItem("Quit", on_quit)
    )
    return pystray.Icon("PizzaTools", image, "Pizza Tools", menu)
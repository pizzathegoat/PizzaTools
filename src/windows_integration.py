import os
import sys
import winreg
import ctypes
from ctypes import wintypes

from PIL import Image

try:
    import pystray
except ImportError:
    pystray = None


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
        ("planes", wintypes.WORD), ("bits", wintypes.WORD),
        ("compression", wintypes.DWORD), ("image_size", wintypes.DWORD),
        ("x_pixels", wintypes.LONG), ("y_pixels", wintypes.LONG),
        ("colors_used", wintypes.DWORD), ("colors_important", wintypes.DWORD),
    ]


def draw_layered_image(window, image, x, y):
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    hwnd = user.GetAncestor(window.winfo_id(), 2)
    user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user.SetWindowLongW(hwnd, -20, user.GetWindowLongW(hwnd, -20) | 0x80000)

    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(_BitmapInfo), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    user.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        wintypes.COLORREF, ctypes.c_void_p, wintypes.DWORD,
    ]

    width, height = image.size
    info = _BitmapInfo(ctypes.sizeof(_BitmapInfo), width, -height, 1, 32)
    bits = ctypes.c_void_p()
    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        raise ctypes.WinError(ctypes.get_last_error())
    bitmap = previous = None
    try:
        bitmap = gdi.CreateDIBSection(dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        if not bitmap:
            raise ctypes.WinError(ctypes.get_last_error())
        red, green, blue, alpha = image.convert("RGBa").split()
        pixels = Image.merge("RGBA", (blue, green, red, alpha)).tobytes()
        ctypes.memmove(bits, pixels, len(pixels))
        previous = gdi.SelectObject(dc, bitmap)
        if not previous:
            raise ctypes.WinError(ctypes.get_last_error())
        position = wintypes.POINT(x, y)
        size = wintypes.SIZE(width, height)
        origin = wintypes.POINT(0, 0)
        blend = (ctypes.c_ubyte * 4)(0, 0, 255, 1)
        if not user.UpdateLayeredWindow(
            hwnd, None, ctypes.byref(position), ctypes.byref(size), dc,
            ctypes.byref(origin), 0, blend, 2,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        move_layered_image(hwnd, x, y, show=True)
        return hwnd
    finally:
        if previous:
            gdi.SelectObject(dc, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def move_layered_image(hwnd, x, y, *, show=False):
    set_position = ctypes.windll.user32.SetWindowPos
    set_position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
    no_resize_or_activation = 0x0001 | 0x0010
    flags = no_resize_or_activation | (0x0040 if show else 0x0004)
    set_position(hwnd, -1 if show else None, x, y, 0, 0, flags)


def create_tray_icon(image, on_show, on_quit):
    if pystray is None:
        return None
    try:
        menu = pystray.Menu(
            pystray.MenuItem("Show App", on_show, default=True),
            pystray.MenuItem("Exit", on_quit)
        )
        return pystray.Icon("PizzaTools", image, "Pizza Tools", menu)
    except Exception:
        return None


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


def create_desktop_shortcut():
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.exists(desktop):
            return False

        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        parent_dir = os.path.dirname(base_dir) if os.path.basename(base_dir) == "src" else base_dir
        main_pyw = os.path.join(parent_dir, "main.pyw")
        if not os.path.exists(main_pyw):
            main_pyw = os.path.abspath(sys.argv[0])

        icon_path = os.path.join(parent_dir, "Pictures", "app_icon.ico")
        target_lnk = os.path.join(desktop, "Pizza Tools.lnk")

        pythonw_exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = sys.executable

        vbs_script = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{target_lnk}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{pythonw_exe}"
oLink.Arguments = """{main_pyw}"""
oLink.WorkingDirectory = "{parent_dir}"
oLink.IconLocation = "{icon_path},0"
oLink.Save
'''
        import tempfile
        import subprocess
        vbs_path = os.path.join(tempfile.gettempdir(), "create_pt_shortcut.vbs")
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_script)

        subprocess.run(["cscript", "//nologo", vbs_path], check=True, creationflags=0x08000000)
        try:
            os.remove(vbs_path)
        except Exception:
            pass
        return True
    except Exception:
        return False

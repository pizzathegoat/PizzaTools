import ctypes

from src.app import LuaUploader


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    try:
        myappid = 'pizzathegoat.pizzatools.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = LuaUploader()
    app.mainloop()


if __name__ == "__main__":
    main()
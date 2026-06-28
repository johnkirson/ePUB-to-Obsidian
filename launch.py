"""Launch the ePUB → Obsidian web UI and open it in the browser.

Double-click ``run.bat`` (Windows) or run ``python launch.py``.
"""

import socket
import sys
import threading
import webbrowser


def _run_folder_picker():
    """Show a native folder dialog and print the chosen path. Used by the
    packaged exe (invoked as ``app.exe --pick-folder``) so Tkinter runs in its
    own process and can't crash the server. The import here also makes
    PyInstaller bundle Tkinter."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(title="Choose output folder")
    finally:
        root.destroy()
    print(path or "")


# Handle the folder-picker sub-invocation before importing/starting Flask.
if "--pick-folder" in sys.argv:
    _run_folder_picker()
    sys.exit(0)

# Windows consoles default to a legacy codepage; force UTF-8 for status output.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from epub2obsidian.server import app


def _free_port(preferred=5000):
    """Return ``preferred`` if free, otherwise an OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"ePUB → Obsidian running at {url}")
    print("Закройте это окно, чтобы остановить приложение.")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # threaded=True so file uploads + the native folder dialog don't block.
    app.run(host="127.0.0.1", port=port, threaded=True)


if __name__ == "__main__":
    main()

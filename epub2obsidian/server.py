"""Flask web UI for the ePUB → Obsidian converter.

Serves a single drag-and-drop page and a small JSON API. Designed to run
locally (127.0.0.1) for a single user, so it can write directly to disk and
open native dialogs / Explorer on the same machine.
"""

import os
import sys
import tempfile
import traceback

from flask import Flask, jsonify, request, send_from_directory

from .converter import (
    DEFAULT_METADATA,
    DEFAULT_RESOURCES,
    check_pandoc,
    convert_book,
    resource_dir,
)

# Bundled assets (templates/, webui/) live under the resource dir, which is the
# PyInstaller temp dir when frozen. The default *output* folder, however, must
# be somewhere persistent: next to the .exe when frozen, else the repo root.
_WEBUI_DIR = os.path.join(resource_dir(), "webui")
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT = os.path.join(_APP_DIR, "output")

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return send_from_directory(_WEBUI_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(_WEBUI_DIR, filename)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.route("/api/health")
def health():
    return jsonify({
        "pandoc": check_pandoc(),
        "default_output": _DEFAULT_OUTPUT,
    })


@app.route("/api/convert", methods=["POST"])
def convert():
    files = request.files.getlist("books")
    if not files:
        return jsonify({"error": "No files uploaded."}), 400

    output_dir = request.form.get("output_dir", "").strip() or _DEFAULT_OUTPUT
    heading_level = request.form.get("heading_level", "auto").strip() or "auto"
    # Optional single-book title override (only meaningful for one file).
    title_override = request.form.get("book_title", "").strip() or None

    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            name = os.path.basename(f.filename or "book.epub")
            stem = os.path.splitext(name)[0]
            tmp_epub = os.path.join(tmpdir, name)
            f.save(tmp_epub)

            # Each book gets its own subfolder under the chosen output dir.
            book_out = os.path.join(output_dir, stem)
            book_title = title_override if len(files) == 1 else stem

            log_lines = []
            try:
                summary = convert_book(
                    tmp_epub,
                    book_out,
                    heading_level=heading_level,
                    metadata_path=DEFAULT_METADATA,
                    resources_path=DEFAULT_RESOURCES,
                    book_title=book_title,
                    log=log_lines.append,
                )
                results.append({
                    "book": stem,
                    "ok": True,
                    "output_path": summary["output_dir"],
                    "count": summary["count"],
                    "log": log_lines,
                })
            except Exception as exc:  # surface the real error to the UI
                log_lines.append(f"[ERROR] {exc}")
                results.append({
                    "book": stem,
                    "ok": False,
                    "error": str(exc),
                    "log": log_lines,
                    "trace": traceback.format_exc(),
                })

    return jsonify({"results": results})


@app.route("/api/open-folder", methods=["POST"])
def open_folder():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Folder not found."}), 400
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 - local, user-initiated
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", path], check=False)
        else:
            import subprocess
            subprocess.run(["xdg-open", path], check=False)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/pick-folder", methods=["POST"])
def pick_folder():
    """Open a native folder picker on this machine.

    Tkinter is not thread-safe and crashes when driven from a Flask worker
    thread, which would take the whole server down. So we run the dialog in a
    short-lived *subprocess* (its own main thread) and read the chosen path
    from stdout — robust and isolated.
    """
    try:
        path = _pick_folder_subprocess()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"path": path or ""})


_PICKER_SCRIPT = (
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk()\n"
    "r.withdraw()\n"
    "r.attributes('-topmost', True)\n"
    "p = filedialog.askdirectory(title='Choose output folder')\n"
    "r.destroy()\n"
    "print(p or '')\n"
)


def _pick_folder_subprocess():
    import subprocess

    if getattr(sys, "frozen", False):
        # Re-invoke our own packaged exe with a flag that just shows the dialog
        # (running `exe -c <script>` would relaunch the whole app instead).
        cmd = [sys.executable, "--pick-folder"]
    else:
        cmd = [sys.executable, "-c", _PICKER_SCRIPT]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return (result.stdout or "").strip()

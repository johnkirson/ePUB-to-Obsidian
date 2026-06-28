"""Reusable ePUB → Obsidian Markdown conversion pipeline.

The pipeline mirrors the original four-step CLI workflow:

  1. Convert an ePUB (or PDF) to a single Markdown file via Pandoc, extracting media.
  2. Split that Markdown into per-heading note files (filename = heading text).
  3. Prepend YAML front matter (from a template) to each note.
  4. Append a "Resources" section to each note, linking to the next note.

Every step accepts a ``log`` callable so callers (CLI or web UI) can capture
progress instead of printing straight to stdout.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile


def resource_dir():
    """Base dir for bundled data (templates/, webui/).

    When packaged with PyInstaller the data lives under ``sys._MEIPASS``;
    otherwise it's the repository root next to this package.
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_RESOURCE_DIR = resource_dir()
DEFAULT_METADATA = os.path.join(_RESOURCE_DIR, "templates", "metadata.yml")
DEFAULT_RESOURCES = os.path.join(_RESOURCE_DIR, "templates", "resources.md")

# Characters that are illegal in Windows filenames (spaces are kept on purpose).
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')


# Common Windows install locations to fall back on when Pandoc isn't on PATH
# yet (e.g. right after `winget install`, before the shell PATH refreshes).
_PANDOC_FALLBACKS = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Pandoc", "pandoc.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Pandoc", "pandoc.exe"),
]


def pandoc_exe():
    """Locate the Pandoc executable, on PATH or in a standard install dir."""
    found = shutil.which("pandoc")
    if found:
        return found
    for candidate in _PANDOC_FALLBACKS:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def check_pandoc():
    """Return the installed Pandoc version string, or ``None`` if not found."""
    exe = pandoc_exe()
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        first_line = out.stdout.splitlines()[0] if out.stdout else ""
        return first_line.strip() or "pandoc (version unknown)"
    except Exception:
        return None


def sanitize_filename(text):
    """Strip filesystem-illegal characters from a heading, keeping it readable."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("", text).strip()
    # Trailing dots/spaces are illegal as Windows filenames.
    return cleaned.rstrip(" .")


_HEADING_RE = re.compile(r"^(#{1,6}) \S")


def detect_heading_level(md_path):
    """Pick the best heading level to split on for an arbitrary book.

    Prefers the shallowest level that yields multiple sections (usually the
    chapter level). Falls back to whichever level has the most headings.
    Returns an int 1-6, or ``None`` if the document has no headings at all.
    """
    counts = {}
    with open(md_path, "r", encoding="utf-8") as f:
        for line in f:
            m = _HEADING_RE.match(line)
            if m:
                lvl = len(m.group(1))
                counts[lvl] = counts.get(lvl, 0) + 1
    if not counts:
        return None
    for lvl in sorted(counts):
        if counts[lvl] >= 2:
            return lvl
    # Only single headings anywhere — split on the most common one.
    return max(counts, key=counts.get)


def _write_single_note(md_path, outdir_path, title, log=print):
    """Write the whole converted Markdown as one note (no usable headings)."""
    os.makedirs(outdir_path, exist_ok=True)
    with open(md_path, "r", encoding="utf-8") as f:
        body = f.read()
    safe = sanitize_filename(title) or "Untitled"
    note_path = os.path.join(outdir_path, f"{safe}.md")
    # Ensure the note opens with a heading so it reads well in Obsidian.
    if not body.lstrip().startswith("#"):
        body = f"# {title}\n\n{body}"
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(body)
    log("[Step 2] No usable headings — wrote the whole book as a single note.")
    return [note_path]


def convert_to_markdown(epub_path, attachments_dir, outfile_path, log=print):
    """Step 1: Pandoc-convert an ePUB/PDF into a single Markdown file."""
    os.makedirs(attachments_dir, exist_ok=True)
    exe = pandoc_exe() or "pandoc"
    pandoc_command = [
        exe,
        "-t", "gfm-raw_html",
        "--wrap=none",
        f"--extract-media={attachments_dir}",
        "-s", epub_path,
        "-o", outfile_path,
    ]
    log(f"[Step 1] Converting to Markdown: {os.path.basename(epub_path)}")
    result = subprocess.run(pandoc_command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Pandoc failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    log("[+] Step 1 done.")


def split_markdown(outfile_path, outdir_path, heading_lvl, log=print):
    """Step 2: Split a single Markdown file into per-heading note files.

    Returns the list of created note paths, in document order.
    """
    log(f"[Step 2] Splitting on heading level {heading_lvl}...")
    os.makedirs(outdir_path, exist_ok=True)

    with open(outfile_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    heading_str = "#" * int(heading_lvl)
    split_indices = [
        idx for idx, line in enumerate(lines)
        if line.startswith(heading_str + " ")
    ]
    if not split_indices:
        log(f"[Step 2] No level-{heading_lvl} headings found. Skipping split.")
        return []

    note_file_paths = []
    used_names = {}
    for i, start_index in enumerate(split_indices):
        end_index = split_indices[i + 1] if (i + 1) < len(split_indices) else len(lines)
        chunk_lines = lines[start_index:end_index]
        heading_text = chunk_lines[0].lstrip("#").strip()
        safe_heading = sanitize_filename(heading_text) or f"note-{i + 1}"

        # Guard against duplicate headings overwriting each other.
        name = safe_heading
        if name in used_names:
            used_names[name] += 1
            name = f"{safe_heading} ({used_names[safe_heading]})"
        else:
            used_names[name] = 0

        note_file_path = os.path.join(outdir_path, f"{name}.md")
        with open(note_file_path, "w", encoding="utf-8") as note_file:
            note_file.write("\n".join(chunk_lines))
            note_file.write("\n")
        note_file_paths.append(note_file_path)

    log(f"[+] Step 2 done. Created {len(note_file_paths)} note(s).")
    return note_file_paths


def prepend_metadata(note_files, metadata_path, book_title=None, log=print):
    """Step 3: Prepend YAML front matter to each note.

    If ``book_title`` is given, fill the template's ``Book: ""`` field with it.
    """
    log("[Step 3] Prepending YAML metadata...")
    with open(metadata_path, "r", encoding="utf-8") as f:
        yaml_template = f.read().strip()

    if book_title:
        safe_title = book_title.replace('"', "'")
        yaml_template = re.sub(
            r'^Book:\s*"".*$',
            f'Book: "{safe_title}"',
            yaml_template,
            count=1,
            flags=re.MULTILINE,
        )

    for note_path in note_files:
        if note_path.lower().endswith(".md"):
            with open(note_path, "r", encoding="utf-8") as note_file:
                original = note_file.read()
            with open(note_path, "w", encoding="utf-8") as note_file:
                note_file.write(f"{yaml_template}\n\n{original}")
    log("[+] Step 3 done.")


def append_resources(note_files, resources_path, log=print):
    """Step 4: Append a Resources section with a link to the next note."""
    log("[Step 4] Appending Resources section...")
    with open(resources_path, "r", encoding="utf-8") as f:
        resources_base = f.read().strip()

    for i, current_note in enumerate(note_files):
        if i < len(note_files) - 1:
            next_name = os.path.splitext(os.path.basename(note_files[i + 1]))[0]
            next_note_link = f"[[{next_name}]]"
        else:
            next_note_link = "N/A"
        resources_content = resources_base.replace("<NEXT_NOTE_LINK>", next_note_link)
        with open(current_note, "r", encoding="utf-8") as note_file:
            original = note_file.read()
        with open(current_note, "w", encoding="utf-8") as note_file:
            note_file.write(f"{original}\n\n{resources_content}\n")
    log("[+] Step 4 done.")


def convert_book(
    epub_path,
    output_dir,
    *,
    heading_level="1",
    metadata_path=DEFAULT_METADATA,
    resources_path=DEFAULT_RESOURCES,
    book_title=None,
    log=print,
):
    """Run the full pipeline for a single book.

    Notes are written into ``output_dir`` and media into
    ``output_dir/attachments``. Returns a summary dict.
    """
    if check_pandoc() is None:
        raise RuntimeError(
            "Pandoc is not installed or not on PATH. "
            "Install it from https://pandoc.org/installing.html"
        )

    epub_path = os.path.abspath(epub_path)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if book_title is None:
        book_title = os.path.splitext(os.path.basename(epub_path))[0]

    attachments_dir = os.path.join(output_dir, "attachments")

    # Intermediate single-file Markdown lives in a temp file; the user only
    # cares about the split notes.
    with tempfile.NamedTemporaryFile(
        suffix=".md", delete=False, dir=output_dir
    ) as tmp:
        intermediate_md = tmp.name

    try:
        convert_to_markdown(epub_path, attachments_dir, intermediate_md, log=log)

        # Decide how to split. "auto" inspects the book; a number forces a level.
        if str(heading_level).lower() == "auto":
            level = detect_heading_level(intermediate_md)
            if level:
                log(f"[Step 2] Auto-detected heading level {level}.")
        else:
            level = int(heading_level)

        if level is None:
            notes = _write_single_note(intermediate_md, output_dir, book_title, log=log)
        else:
            notes = split_markdown(intermediate_md, output_dir, level, log=log)
            if not notes:
                # Chosen level didn't match this book — never leave the user
                # empty-handed; fall back to the whole book as one note.
                notes = _write_single_note(intermediate_md, output_dir, book_title, log=log)

        prepend_metadata(notes, metadata_path, book_title=book_title, log=log)
        append_resources(notes, resources_path, log=log)
    finally:
        if os.path.exists(intermediate_md):
            os.remove(intermediate_md)

    return {
        "book": book_title,
        "output_dir": output_dir,
        "attachments_dir": attachments_dir,
        "notes": notes,
        "count": len(notes),
    }

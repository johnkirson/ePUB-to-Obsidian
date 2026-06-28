"""ePUB → Obsidian Markdown converter package.

Exposes the reusable conversion pipeline and a small Flask web UI.
"""

from .converter import convert_book, check_pandoc

__all__ = ["convert_book", "check_pandoc"]
__version__ = "1.0.0"

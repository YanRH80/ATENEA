"""
atenea/web/components/header.py — Minimal navigation bar

Anki-inspired: thin bar, no clutter. Just branding + context + back.
"""

from nicegui import ui

from atenea.web import theme
from atenea import __version__


def render_header(context=None, back_url=None):
    """Render a thin header bar.

    Args:
        context: Optional context string (e.g. project name in test/analysis)
        back_url: If set, show a back arrow linking to this URL
    """
    with ui.header().classes("bg-slate-900/80 border-b border-slate-800"):
        with ui.row().classes("w-full items-center px-4 py-1"):
            # Back arrow (if in sub-view)
            if back_url:
                ui.button(
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to(back_url),
                ).props("flat dense round color=grey-6").classes("mr-2")

            # Logo
            ui.link("ATENEA", "/").classes(
                "text-lg font-bold text-blue-400 no-underline hover:text-blue-300"
            )

            # Context
            if context:
                ui.label("›").classes("text-slate-600 mx-2")
                ui.label(context).classes("text-sm text-slate-400")

            ui.space()

            # Version (subtle)
            ui.label(f"v{__version__}").classes("text-xs text-slate-600")

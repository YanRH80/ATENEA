"""
atenea/web/components/header.py — Navigation header bar
"""

from nicegui import ui

from atenea.web import theme


def render_header(current_project=None):
    """Render the top navigation bar."""
    with ui.header().classes("bg-slate-900 border-b border-slate-700"):
        with ui.row().classes("w-full items-center px-4 py-2"):
            # Logo / Home link
            ui.link("ATENEA", "/").classes(
                "text-xl font-bold text-blue-400 no-underline hover:text-blue-300"
            )

            ui.label("|").classes("text-slate-600 mx-2")
            ui.label("Adaptive learning from medical documents").classes(
                "text-sm text-slate-400"
            )

            # Breadcrumb
            if current_project:
                ui.label("/").classes("text-slate-600 mx-2")
                ui.link(
                    current_project.upper(),
                    f"/project/{current_project}",
                ).classes("text-sm text-slate-300 no-underline hover:text-blue-300")

            # Spacer
            ui.space()

            # About link
            ui.link("?", "/about").classes(
                "text-slate-400 no-underline hover:text-blue-300 "
                "border border-slate-600 rounded px-2 py-1 text-xs"
            )

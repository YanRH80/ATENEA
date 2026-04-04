"""
atenea/web/pages/home.py — Homepage with project list
"""

from nicegui import ui

from atenea.web import theme
from atenea.web.components.header import render_header
from atenea.services.project_service import list_projects_with_stats


def render():
    """Render the homepage."""
    render_header()

    with ui.column().classes("w-full max-w-4xl mx-auto px-6 py-8"):
        # Title
        ui.label("Proyectos").classes("text-2xl font-bold text-slate-100 mb-6")

        projects = list_projects_with_stats()

        if not projects:
            with ui.card().classes("bg-slate-800 w-full p-8"):
                ui.label("No hay proyectos todavia.").classes("text-slate-400 text-lg")
                ui.label(
                    "Crea un proyecto desde la CLI: atenea"
                ).classes("text-slate-500 text-sm mt-2")
            return

        for p in projects:
            _render_project_card(p)


def _render_project_card(p):
    """Render a single project card."""
    with ui.card().classes(
        "bg-slate-800 w-full mb-4 cursor-pointer hover:bg-slate-750 "
        "border border-slate-700 hover:border-blue-500 transition-colors"
    ).on("click", lambda _, name=p["name"]: ui.navigate.to(f"/project/{name}")):

        with ui.row().classes("w-full items-center justify-between"):
            # Project name + stats
            with ui.column().classes("gap-1"):
                ui.label(p["name"].upper()).classes(
                    "text-lg font-bold text-blue-400"
                )

                with ui.row().classes("gap-4 text-sm"):
                    ui.label(f"{p['n_sources']} docs").classes("text-slate-400")
                    ui.label(f"{p['n_knowledge']} conceptos").classes("text-slate-400")
                    ui.label(f"{p['n_questions']} preguntas").classes("text-slate-400")

                # Last sync
                last_sync = p["last_sync"]
                if last_sync != "never":
                    ui.label(f"Sync: {last_sync[:10]}").classes("text-xs text-slate-500")

            # Coverage indicator
            with ui.column().classes("items-end gap-1"):
                if p["coverage_pct"] is not None:
                    pct = p["coverage_pct"]
                    color = theme.KNOWN if pct >= 70 else theme.TESTING if pct >= 40 else theme.UNKNOWN
                    ui.label(f"{pct}%").classes("text-2xl font-bold").style(f"color: {color}")
                    ui.label("dominio").classes("text-xs text-slate-500")
                else:
                    ui.label("--").classes("text-2xl font-bold text-slate-600")
                    ui.label("sin test").classes("text-xs text-slate-500")

        # Progress checklist (compact)
        with ui.row().classes("w-full gap-3 mt-3 text-xs"):
            _step_badge("Sync", p["n_sources"] > 0)
            _step_badge("Study", p["has_knowledge"])
            _step_badge("Generate", p["has_questions"])
            _step_badge("Test", p["has_coverage"])


def _step_badge(label, done):
    """Small badge showing pipeline step completion."""
    if done:
        ui.label(f"[x] {label}").classes(
            "text-green-400 bg-green-900/30 rounded px-2 py-0.5"
        )
    else:
        ui.label(f"[ ] {label}").classes(
            "text-slate-500 bg-slate-700/30 rounded px-2 py-0.5"
        )

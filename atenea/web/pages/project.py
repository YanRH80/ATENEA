"""
atenea/web/pages/project.py — Project dashboard
"""

from nicegui import ui

from atenea.web import theme
from atenea.web.components.header import render_header
from atenea.web.components.knowledge_graph import render_graph
from atenea.services.project_service import get_project_overview, get_knowledge_graph_data
from atenea.services.review_service import get_session_history


def render(project_name: str):
    """Render the project dashboard."""
    render_header(current_project=project_name)

    overview = get_project_overview(project_name)
    graph_data = get_knowledge_graph_data(project_name)
    sessions = get_session_history(project_name)

    with ui.column().classes("w-full max-w-5xl mx-auto px-6 py-8"):
        # Project header
        with ui.row().classes("w-full items-center justify-between mb-6"):
            ui.label(project_name.upper()).classes("text-3xl font-bold text-blue-400")

            # Quick action buttons
            with ui.row().classes("gap-2"):
                _action_button(
                    "Test",
                    f"/project/{project_name}/test",
                    overview["has_questions"],
                    "Iniciar test interactivo",
                )
                _action_button(
                    "Grafo",
                    f"/project/{project_name}/graph",
                    overview["has_knowledge"],
                    "Ver grafo completo",
                )

        # Auto-suggest next step
        _render_next_step(overview, project_name)

        # Stats row
        with ui.row().classes("w-full gap-4 mb-6"):
            _stat_card("Documentos", overview["n_sources"], "docs sincronizados")
            _stat_card("Conceptos", overview["n_knowledge"],
                       f"{overview['n_keywords']} kw + {overview['n_associations']} rel + {overview['n_sequences']} seq")
            _stat_card("Preguntas", overview["n_questions"], "tipo MIR/ENARM")
            _stat_card(
                "Dominio",
                f"{overview['coverage_pct']}%" if overview['coverage_pct'] is not None else "--",
                f"{overview['known']}/{overview['total']} conocidos" if overview['total'] > 0 else "sin test",
            )

        # Session history
        if sessions:
            with ui.card().classes("bg-slate-800 w-full p-4 mb-6 border border-slate-700"):
                ui.label("Historial de sesiones").classes("text-lg font-semibold text-slate-200 mb-3")
                _render_session_chart(sessions)

        # Knowledge graph (mini version)
        if graph_data.get("nodes"):
            with ui.card().classes("bg-slate-800 w-full p-4 border border-slate-700"):
                with ui.row().classes("items-center justify-between mb-2"):
                    ui.label("Grafo de conocimiento").classes("text-lg font-semibold text-slate-200")
                    hub_terms = graph_data.get("stats", {}).get("hub_terms", [])
                    if hub_terms:
                        hubs = ", ".join(h["term"] for h in hub_terms[:3])
                        ui.label(f"Hubs: {hubs}").classes("text-xs text-slate-400")

                render_graph(graph_data, height="350px", mini=True)

                with ui.row().classes("justify-center mt-2"):
                    ui.link(
                        "Ver grafo completo →",
                        f"/project/{project_name}/graph"
                    ).classes("text-sm text-blue-400 no-underline hover:text-blue-300")


def _render_next_step(overview, project_name):
    """Show auto-suggestion for next pipeline step."""
    if overview["n_sources"] == 0:
        msg = "Siguiente paso: Sincroniza documentos desde Zotero (CLI: atenea)"
        color = "blue"
    elif not overview["has_knowledge"]:
        msg = "Siguiente paso: Extraer conocimiento (CLI: atenea → Estudiar)"
        color = "blue"
    elif not overview["has_questions"]:
        msg = "Siguiente paso: Generar preguntas (CLI: atenea → Generar)"
        color = "blue"
    elif not overview["has_coverage"]:
        msg = f"Listo para test: {overview['n_questions']} preguntas disponibles"
        color = "green"
    else:
        pending = overview["total"] - overview["known"]
        if pending > 0:
            msg = f"{pending} conceptos pendientes de repaso"
            color = "yellow"
        else:
            msg = "Dominio completo. Genera mas preguntas para profundizar."
            color = "green"

    ui.label(msg).classes(
        f"text-sm px-3 py-2 rounded mb-4 bg-{color}-900/30 text-{color}-400 "
        "border border-opacity-30"
    ).style(f"border-color: {getattr(theme, color.upper(), theme.PRIMARY)}")


def _stat_card(title, value, subtitle):
    """Render a compact stat card."""
    with ui.card().classes("bg-slate-800 flex-1 p-4 border border-slate-700"):
        ui.label(str(value)).classes("text-2xl font-bold text-slate-100")
        ui.label(title).classes("text-sm font-semibold text-slate-300")
        ui.label(subtitle).classes("text-xs text-slate-500")


def _action_button(label, target, enabled, tooltip):
    """Render an action button."""
    if enabled:
        ui.button(label, on_click=lambda: ui.navigate.to(target)).props(
            "flat color=primary"
        ).tooltip(tooltip)
    else:
        ui.button(label).props("flat color=grey disable").tooltip(
            "No disponible aun"
        )


def _render_session_chart(sessions):
    """Render a line chart of session scores over time."""
    if len(sessions) < 2:
        # Just show the last session as text
        s = sessions[-1]
        ui.label(
            f"Ultimo test: {s['correct']}/{s['total']} ({s['score']}%) — {s['date'][:10]}"
        ).classes("text-sm text-slate-300")
        return

    dates = [s["date"][:10] for s in sessions]
    scores = [s["score"] for s in sessions]

    ui.echart({
        "backgroundColor": "transparent",
        "grid": {"top": 20, "bottom": 30, "left": 40, "right": 20},
        "xAxis": {
            "type": "category",
            "data": dates,
            "axisLabel": {"color": theme.TEXT_MUTED, "fontSize": 10},
            "axisLine": {"lineStyle": {"color": theme.BORDER}},
        },
        "yAxis": {
            "type": "value",
            "min": 0,
            "max": 100,
            "axisLabel": {"color": theme.TEXT_MUTED, "formatter": "{value}%"},
            "splitLine": {"lineStyle": {"color": theme.SURFACE, "type": "dashed"}},
        },
        "series": [{
            "data": scores,
            "type": "line",
            "smooth": True,
            "lineStyle": {"color": theme.PRIMARY, "width": 2},
            "itemStyle": {"color": theme.PRIMARY},
            "areaStyle": {"color": f"{theme.PRIMARY}20"},
        }],
        "tooltip": {
            "trigger": "axis",
            "formatter": "{b}<br/>Score: {c}%",
            "backgroundColor": theme.CARD_BG,
            "borderColor": theme.BORDER,
            "textStyle": {"color": theme.TEXT},
        },
    }).classes("w-full").style("height: 180px")

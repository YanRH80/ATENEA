"""
atenea/web/pages/graph.py — Full knowledge graph visualization
"""

from nicegui import ui

from atenea.web import theme
from atenea.web.components.header import render_header
from atenea.web.components.knowledge_graph import render_graph
from atenea.services.project_service import get_knowledge_graph_data


def render(project_name: str):
    """Render the full knowledge graph page."""
    render_header(current_project=project_name)

    graph_data = get_knowledge_graph_data(project_name)
    stats = graph_data.get("stats", {})

    with ui.column().classes("w-full max-w-6xl mx-auto px-6 py-8"):
        # Header
        with ui.row().classes("w-full items-center justify-between mb-4"):
            ui.label("Grafo de conocimiento").classes("text-2xl font-bold text-slate-100")

            with ui.row().classes("gap-4 text-sm"):
                ui.label(f"{stats.get('n_nodes', 0)} conceptos").classes("text-slate-400")
                ui.label(f"{stats.get('n_edges', 0)} relaciones").classes("text-slate-400")
                ui.label(f"{stats.get('n_sequences', 0)} secuencias").classes("text-slate-400")

        # Legend
        with ui.row().classes("gap-4 mb-4"):
            _legend_item("Dominado", theme.KNOWN)
            _legend_item("En revision", theme.TESTING)
            _legend_item("Desconocido", theme.UNKNOWN)
            ui.label("| Tamano = conexiones").classes("text-xs text-slate-500")

        # Graph
        if graph_data.get("nodes"):
            render_graph(graph_data, height="600px", mini=False)
        else:
            ui.label("Sin datos. Ejecuta Study desde la CLI.").classes(
                "text-slate-400 italic text-lg py-12"
            )

        # Hub terms
        hub_terms = stats.get("hub_terms", [])
        if hub_terms:
            with ui.card().classes("bg-slate-800 w-full p-4 mt-6 border border-slate-700"):
                ui.label("Conceptos hub (mas conectados)").classes(
                    "text-lg font-semibold text-slate-200 mb-3"
                )
                for h in hub_terms:
                    with ui.row().classes("items-center gap-2"):
                        ui.label(h["term"]).classes("text-sm font-semibold text-blue-400")
                        ui.label(f"{h['connections']} conexiones").classes("text-xs text-slate-500")

        # Sequences
        sequences = graph_data.get("sequences", [])
        if sequences:
            with ui.card().classes("bg-slate-800 w-full p-4 mt-4 border border-slate-700"):
                ui.label(f"Secuencias ({len(sequences)})").classes(
                    "text-lg font-semibold text-slate-200 mb-3"
                )
                for seq in sequences[:10]:
                    nodes = seq.get("nodes", [])
                    chain = " → ".join(nodes)
                    desc = seq.get("description", "")
                    ui.label(chain).classes("text-sm text-cyan-400 font-mono")
                    if desc:
                        ui.label(desc).classes("text-xs text-slate-500 mb-2")


def _legend_item(label, color):
    """Small color legend item."""
    with ui.row().classes("items-center gap-1"):
        ui.element("div").classes("w-3 h-3 rounded-full").style(f"background: {color}")
        ui.label(label).classes("text-xs text-slate-400")

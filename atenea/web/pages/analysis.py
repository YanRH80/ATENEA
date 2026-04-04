"""
atenea/web/pages/analysis.py — Analysis workspace

Design: Obsidian workspace (tabs) + Notion drill-down.
4 tabs: Overview · Grafo · Gaps · Sesiones

All analysis data in one place. No navigation to other pages needed.
"""

from nicegui import ui

from atenea.web import theme
from atenea.web.components.header import render_header
from atenea.web.components.knowledge_graph import render_graph
from atenea.services.project_service import get_project_overview, get_knowledge_graph_data
from atenea.services.review_service import get_session_history, compute_coverage, detect_gaps


def render(project_name: str):
    """Render the analysis workspace."""
    render_header(context=project_name.upper(), back_url="/")

    # Load ALL data upfront (avoid re-fetching per tab)
    overview = get_project_overview(project_name)
    graph_data = get_knowledge_graph_data(project_name)
    sessions = get_session_history(project_name)
    coverage = compute_coverage(project_name)
    gaps = detect_gaps(project_name)

    with ui.column().classes("w-full max-w-6xl mx-auto px-4 py-4"):

        # ── Tabs ─────────────────────────────────────────────
        with ui.tabs().classes("w-full").props("dense active-color=primary indicator-color=primary") as tabs:
            overview_tab = ui.tab("overview", label="Overview")
            graph_tab = ui.tab("graph", label="Grafo")
            gaps_tab = ui.tab("gaps", label="Gaps")
            sessions_tab = ui.tab("sessions", label="Sesiones")

        with ui.tab_panels(tabs, value=overview_tab).classes("w-full"):

            # ── TAB 1: Overview ──────────────────────────────
            with ui.tab_panel(overview_tab):
                _render_overview(overview, coverage, graph_data, project_name)

            # ── TAB 2: Knowledge Graph ───────────────────────
            with ui.tab_panel(graph_tab):
                _render_graph_tab(graph_data)

            # ── TAB 3: Gaps ──────────────────────────────────
            with ui.tab_panel(gaps_tab):
                _render_gaps_tab(gaps, coverage)

            # ── TAB 4: Sessions ──────────────────────────────
            with ui.tab_panel(sessions_tab):
                _render_sessions_tab(sessions, project_name)


# ============================================================
# TAB 1: OVERVIEW
# ============================================================

def _render_overview(overview, coverage, graph_data, project_name):
    """Dense stats overview + coverage breakdown + quick actions."""

    # ── Stats grid ───────────────────────────────────────
    with ui.row().classes("w-full gap-3 mb-6"):
        _stat(
            overview["n_sources"], "documentos",
            "Fuentes sincronizadas",
        )
        _stat(
            overview["n_keywords"], "keywords",
            f"+ {overview['n_associations']} relaciones + {overview['n_sequences']} secuencias",
        )
        _stat(
            overview["n_questions"], "preguntas",
            "tipo MIR/ENARM",
        )
        # Coverage with color
        pct = overview.get("coverage_pct")
        if pct is not None:
            color = theme.KNOWN if pct >= 70 else theme.TESTING if pct >= 40 else theme.UNKNOWN
            _stat(f"{pct}%", "dominio", f"{overview['known']}/{overview['total']} conceptos", color=color)
        else:
            _stat("—", "dominio", "sin test aún")

    # ── Coverage breakdown by type ───────────────────────
    summary = coverage.get("summary", {})
    if any(s.get("total", 0) > 0 for s in summary.values()):
        with ui.card().classes("bg-slate-800/40 w-full p-4 border border-slate-700/50 mb-4"):
            ui.label("Cobertura por tipo").classes("text-sm font-semibold text-slate-400 mb-3")

            for type_name, display_name in [("keywords", "Keywords"), ("associations", "Relaciones"), ("sequences", "Secuencias")]:
                s = summary.get(type_name, {})
                total = s.get("total", 0)
                if total == 0:
                    continue

                known = s.get("known", 0)
                testing = s.get("testing", 0)
                unknown = s.get("unknown", 0)

                known_pct = known / total * 100
                testing_pct = testing / total * 100
                unknown_pct = unknown / total * 100

                with ui.row().classes("w-full items-center gap-3 mb-2"):
                    ui.label(display_name).classes("text-xs text-slate-400 min-w-[80px]")
                    theme.html(f'''
                        <div class="mastery-bar" style="flex:1; height:6px;" title="{known}✓ {testing}~ {unknown}?">
                            <div class="known" style="width:{known_pct}%"></div>
                            <div class="testing" style="width:{testing_pct}%"></div>
                            <div class="unknown" style="width:{unknown_pct}%"></div>
                        </div>
                    ''').classes("flex-1")
                    ui.label(f"{known}/{total}").classes("text-xs text-slate-500 font-mono min-w-[50px] text-right")

    # ── Coverage breakdown by source ─────────────────────
    by_source = coverage.get("by_source", {})
    if by_source:
        with ui.card().classes("bg-slate-800/40 w-full p-4 border border-slate-700/50 mb-4"):
            ui.label("Cobertura por fuente").classes("text-sm font-semibold text-slate-400 mb-3")

            for source, s in sorted(by_source.items(), key=lambda x: -x[1]["total"]):
                total = s["total"]
                known = s["known"]
                testing = s["testing"]
                unknown = s["unknown"]

                known_pct = known / total * 100 if total > 0 else 0
                testing_pct = testing / total * 100 if total > 0 else 0

                with ui.row().classes("w-full items-center gap-3 mb-2"):
                    # Truncate source name
                    display_source = source[:30] + "…" if len(source) > 30 else source
                    ui.label(display_source).classes("text-xs text-slate-400 min-w-[120px]").tooltip(source)
                    theme.html(f'''
                        <div class="mastery-bar" style="flex:1; height:6px;">
                            <div class="known" style="width:{known_pct}%"></div>
                            <div class="testing" style="width:{testing_pct}%"></div>
                            <div class="unknown" style="width:{100 - known_pct - testing_pct}%"></div>
                        </div>
                    ''').classes("flex-1")
                    ui.label(f"{known}/{total}").classes("text-xs text-slate-500 font-mono min-w-[50px] text-right")

    # ── Hub terms (quick insight) ────────────────────────
    hub_terms = graph_data.get("stats", {}).get("hub_terms", [])
    if hub_terms:
        with ui.card().classes("bg-slate-800/40 w-full p-4 border border-slate-700/50 mb-4"):
            ui.label("Conceptos hub (más conectados)").classes("text-sm font-semibold text-slate-400 mb-3")
            with ui.row().classes("gap-3 flex-wrap"):
                for h in hub_terms:
                    ui.label(f"{h['term']} ({h['connections']})").classes(
                        "text-xs text-blue-400 bg-blue-900/20 rounded px-2 py-1"
                    )

    # ── Sequences (quick insight) ────────────────────────
    sequences = graph_data.get("sequences", [])
    if sequences:
        with ui.card().classes("bg-slate-800/40 w-full p-4 border border-slate-700/50"):
            ui.label(f"Secuencias ({len(sequences)})").classes("text-sm font-semibold text-slate-400 mb-3")
            for seq in sequences[:8]:
                chain = " → ".join(seq.get("nodes", []))
                desc = seq.get("description", "")
                ui.label(chain).classes("text-xs text-cyan-400 font-mono")
                if desc:
                    ui.label(desc).classes("text-xs text-slate-600 mb-1")


def _stat(value, label, sublabel, color=None):
    """Compact stat card."""
    with ui.card().classes("bg-slate-800/40 flex-1 p-3 border border-slate-700/50"):
        if color:
            ui.label(str(value)).classes("text-2xl font-bold").style(f"color: {color}")
        else:
            ui.label(str(value)).classes("text-2xl font-bold text-slate-100")
        ui.label(label).classes("text-xs font-semibold text-slate-400")
        ui.label(sublabel).classes("text-xs text-slate-600")


# ============================================================
# TAB 2: KNOWLEDGE GRAPH
# ============================================================

def _render_graph_tab(graph_data):
    """Full knowledge graph + legend + filters + node details."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    stats = graph_data.get("stats", {})
    categories = graph_data.get("categories", [])

    if not nodes:
        ui.label("Sin datos. Extrae conocimiento primero (CLI: atenea → Study).").classes(
            "text-slate-500 italic py-8"
        )
        return

    # Collect filter options
    all_tags = sorted(set(t for n in nodes for t in n.get("tags", [])))
    all_sources = sorted(set(n.get("source", "") for n in nodes if n.get("source")))
    all_statuses = ["known", "testing", "unknown"]

    # Stats + legend bar
    with ui.row().classes("w-full items-center gap-4 mb-2"):
        ui.label(f"{stats.get('n_nodes', 0)} nodos · {stats.get('n_edges', 0)} relaciones · {stats.get('n_sequences', 0)} secuencias").classes("text-xs text-slate-500")
        ui.space()
        _legend_dot("Dominado", theme.KNOWN)
        _legend_dot("En revisión", theme.TESTING)
        _legend_dot("Desconocido", theme.UNKNOWN)
        ui.label("· Tamaño = conexiones").classes("text-xs text-slate-600")

    # Filters
    graph_container = ui.column().classes("w-full")

    filter_status = {"value": None}
    filter_tag = {"value": None}
    filter_source = {"value": None}

    def apply_filters():
        """Re-render graph with filters applied."""
        filtered_nodes = nodes
        if filter_status["value"]:
            filtered_nodes = [n for n in filtered_nodes if n.get("status") == filter_status["value"]]
        if filter_tag["value"]:
            filtered_nodes = [n for n in filtered_nodes if filter_tag["value"] in n.get("tags", [])]
        if filter_source["value"]:
            filtered_nodes = [n for n in filtered_nodes if n.get("source") == filter_source["value"]]

        visible_terms = {n["term"] for n in filtered_nodes}
        filtered_edges = [e for e in edges if e["source"] in visible_terms and e["target"] in visible_terms]

        filtered_data = {
            **graph_data,
            "nodes": filtered_nodes,
            "edges": filtered_edges,
            "stats": {
                **stats,
                "n_nodes": len(filtered_nodes),
                "n_edges": len(filtered_edges),
            },
        }

        graph_container.clear()
        with graph_container:
            if filtered_nodes:
                n_nodes = len(filtered_nodes)
                if n_nodes > 300:
                    ui.label(f"⚠ {n_nodes} nodos — el layout puede ser lento").classes("text-xs text-yellow-400 mb-2")
                render_graph(filtered_data, height="550px", mini=False)
            else:
                ui.label("Sin nodos con estos filtros.").classes("text-slate-500 italic py-4")

    with ui.row().classes("w-full gap-2 mb-3 items-center"):
        ui.label("Filtrar:").classes("text-xs text-slate-500")

        status_select = ui.select(
            options={"": "— Status —", **{s: s.capitalize() for s in all_statuses}},
            value="",
        ).props("dense outlined").classes("min-w-[120px]").style("font-size:12px")

        tag_select = ui.select(
            options={"": "— Tag —", **{t: t for t in all_tags}},
            value="",
        ).props("dense outlined").classes("min-w-[120px]").style("font-size:12px") if all_tags else None

        source_select = ui.select(
            options={"": "— Fuente —", **{s: s[:25] for s in all_sources}},
            value="",
        ).props("dense outlined").classes("min-w-[150px]").style("font-size:12px") if all_sources else None

        ui.button("Reset", on_click=lambda: _reset_filters(
            status_select, tag_select, source_select, filter_status, filter_tag, filter_source, apply_filters
        )).props("flat dense color=grey-5").classes("text-xs")

        def on_status_change(e):
            filter_status["value"] = e.value if e.value else None
            apply_filters()

        def on_tag_change(e):
            filter_tag["value"] = e.value if e.value else None
            apply_filters()

        def on_source_change(e):
            filter_source["value"] = e.value if e.value else None
            apply_filters()

        status_select.on("update:model-value", on_status_change)
        if tag_select:
            tag_select.on("update:model-value", on_tag_change)
        if source_select:
            source_select.on("update:model-value", on_source_change)

    # Initial render
    apply_filters()

    # Node detail table
    if len(nodes) <= 300:
        with ui.expansion("Tabla de nodos", icon="table_chart").classes(
            "w-full mt-4 text-slate-400"
        ).props("dense header-class=text-slate-500"):
            _render_node_table(nodes)


def _reset_filters(status_sel, tag_sel, source_sel, f_status, f_tag, f_source, apply_fn):
    """Reset all filters."""
    status_sel.value = ""
    if tag_sel:
        tag_sel.value = ""
    if source_sel:
        source_sel.value = ""
    f_status["value"] = None
    f_tag["value"] = None
    f_source["value"] = None
    apply_fn()


def _legend_dot(label, color):
    """Tiny legend item."""
    with ui.row().classes("items-center gap-1"):
        theme.html(f'<div style="width:8px;height:8px;border-radius:50%;background:{color}"></div>')
        ui.label(label).classes("text-xs text-slate-500")


def _render_node_table(nodes):
    """Sortable table of all concepts."""
    rows = []
    for n in sorted(nodes, key=lambda x: -x.get("n_connections", 0)):
        sm2 = n.get("sm2") or {}
        reviews = sm2.get("reviews", 0)
        correct = sm2.get("correct", 0)
        ratio = f"{int(correct/reviews*100)}%" if reviews > 0 else "—"

        rows.append({
            "term": n["term"],
            "status": n.get("status", "unknown"),
            "connections": n.get("n_connections", 0),
            "reviews": reviews,
            "ratio": ratio,
            "source": (n.get("source", "")[:20] + "…") if len(n.get("source", "")) > 20 else n.get("source", ""),
        })

    columns = [
        {"name": "term", "label": "Concepto", "field": "term", "sortable": True, "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "sortable": True},
        {"name": "connections", "label": "Conexiones", "field": "connections", "sortable": True},
        {"name": "reviews", "label": "Reviews", "field": "reviews", "sortable": True},
        {"name": "ratio", "label": "Acierto", "field": "ratio", "sortable": True},
        {"name": "source", "label": "Fuente", "field": "source", "sortable": True},
    ]

    ui.table(
        columns=columns,
        rows=rows,
        row_key="term",
    ).classes("w-full").props(
        "dense flat bordered separator=cell "
        "table-header-class=bg-slate-800 "
        "table-class=bg-slate-900"
    ).style(f"color: {theme.TEXT_MUTED}; font-size: 12px;")


# ============================================================
# TAB 3: GAPS
# ============================================================

def _render_gaps_tab(gaps, coverage):
    """Weak areas + recommendations."""
    overall = coverage.get("overall", {})

    # Overall summary
    if overall:
        with ui.row().classes("w-full gap-4 mb-6"):
            _stat(overall.get("total", 0), "conceptos totales", "en knowledge base")
            _stat(
                f"{overall.get('seen_pct', 0)}%",
                "vistos",
                f"{overall.get('seen', 0)}/{overall.get('total', 0)} al menos 1 vez",
            )
            _stat(
                f"{overall.get('known_pct', 0)}%",
                "dominados",
                f"SM-2 status = known",
                color=theme.KNOWN if overall.get('known_pct', 0) >= 70 else theme.TESTING,
            )

    if not gaps:
        ui.label("Sin gaps detectados (necesitas al menos 2 revisiones por concepto).").classes(
            "text-slate-500 italic py-4"
        )
        return

    # Gaps table
    ui.label(f"{len(gaps)} conceptos débiles (<50% acierto con ≥2 revisiones)").classes(
        "text-sm font-semibold text-red-400 mb-3"
    )

    for g in gaps:
        ratio = g["ratio"]
        bar_color = theme.UNKNOWN if ratio < 30 else theme.TESTING

        with ui.row().classes("w-full items-center gap-3 py-2 border-b border-slate-800/50"):
            # Term
            ui.label(g["term"]).classes("text-sm text-slate-300 min-w-[150px] font-semibold")

            # Mini bar
            theme.html(f'''
                <div class="mastery-bar" style="width:80px; height:5px;">
                    <div style="width:{ratio}%; background:{bar_color};"></div>
                </div>
            ''')

            # Stats
            ui.label(f"{ratio}%").classes("text-xs text-red-400 font-mono min-w-[40px]")
            ui.label(f"{g['correct']}/{g['reviews']} rev").classes("text-xs text-slate-500")
            ui.label(f"EF:{g['ef']:.1f}").classes("text-xs text-slate-600 font-mono")


# ============================================================
# TAB 4: SESSIONS
# ============================================================

def _render_sessions_tab(sessions, project_name):
    """Session history chart + table."""

    if not sessions:
        ui.label("Sin sesiones de test registradas.").classes("text-slate-500 italic py-4")
        ui.button(
            "Iniciar primer test",
            on_click=lambda: ui.navigate.to(f"/test/{project_name}"),
        ).props("flat color=primary")
        return

    # Chart (if enough data)
    if len(sessions) >= 2:
        dates = [s["date"][:10] for s in sessions]
        scores = [s["score"] for s in sessions]
        totals = [s["total"] for s in sessions]

        ui.echart({
            "backgroundColor": "transparent",
            "grid": {"top": 30, "bottom": 30, "left": 50, "right": 20},
            "xAxis": {
                "type": "category",
                "data": dates,
                "axisLabel": {"color": theme.TEXT_MUTED, "fontSize": 10, "rotate": 30},
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
                "areaStyle": {"color": f"{theme.PRIMARY}15"},
            }],
            "tooltip": {
                "trigger": "axis",
                "backgroundColor": theme.CARD_BG,
                "borderColor": theme.BORDER,
                "textStyle": {"color": theme.TEXT, "fontSize": 12},
            },
        }).classes("w-full").style("height: 200px")

    # Session table
    ui.label("Historial").classes("text-sm font-semibold text-slate-400 mt-4 mb-2")

    for i, s in enumerate(reversed(sessions)):
        score = s["score"]
        color = theme.KNOWN if score >= 70 else theme.TESTING if score >= 50 else theme.UNKNOWN

        with ui.row().classes("w-full items-center gap-3 py-2 border-b border-slate-800/50"):
            ui.label(f"#{len(sessions) - i}").classes("text-xs text-slate-600 min-w-[30px]")
            ui.label(s["date"][:10]).classes("text-xs text-slate-500 min-w-[80px]")
            ui.label(f"{s['correct']}/{s['total']}").classes("text-sm text-slate-300 min-w-[50px]")

            # Score with color
            ui.label(f"{score}%").classes("text-sm font-bold min-w-[40px]").style(f"color: {color}")

            # Mini bar
            theme.html(f'''
                <div class="mastery-bar" style="flex:1; height:5px;">
                    <div style="width:{score}%; background:{color};"></div>
                </div>
            ''').classes("flex-1")

    # Quick link to test
    ui.button(
        "Nuevo test",
        on_click=lambda: ui.navigate.to(f"/test/{project_name}"),
    ).props("flat color=primary").classes("mt-4")

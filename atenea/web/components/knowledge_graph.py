"""
atenea/web/components/knowledge_graph.py — ECharts knowledge graph visualization
"""

from nicegui import ui

from atenea.web import theme


def render_graph(graph_data, height="500px", mini=False):
    """Render a knowledge graph using ECharts.

    Args:
        graph_data: dict from project_service.get_knowledge_graph_data()
        height: CSS height string
        mini: If True, show simplified version (top hubs only)
    """
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    categories = graph_data.get("categories", [])
    stats = graph_data.get("stats", {})

    if not nodes:
        ui.label("Sin datos de conocimiento. Ejecuta Study primero.").classes(
            "text-slate-400 italic"
        )
        return

    # Filter for mini mode (top connected nodes only)
    if mini:
        hub_terms = {h["term"] for h in stats.get("hub_terms", [])}
        # Include hubs + their direct neighbors
        connected = set()
        for e in edges:
            if e["source"] in hub_terms or e["target"] in hub_terms:
                connected.add(e["source"])
                connected.add(e["target"])
        visible_terms = hub_terms | connected
        nodes = [n for n in nodes if n["term"] in visible_terms]
        edges = [e for e in edges if e["source"] in visible_terms and e["target"] in visible_terms]

    # Build ECharts data
    echart_nodes = []
    term_to_idx = {}
    for i, node in enumerate(nodes):
        term_to_idx[node["term"]] = i
        status = node.get("status", "unknown")
        color = theme.NODE_COLORS.get(status, theme.UNKNOWN)

        # Size based on connections
        n_conn = node.get("n_connections", 0)
        size = max(15, min(40, 15 + n_conn * 4))

        echart_nodes.append({
            "id": str(i),
            "name": node["term"],
            "symbolSize": size,
            "itemStyle": {"color": color},
            "category": node["tags"][0] if node.get("tags") else "general",
            "value": node.get("definition", "")[:80],
        })

    echart_edges = []
    for edge in edges:
        src_idx = term_to_idx.get(edge["source"])
        tgt_idx = term_to_idx.get(edge["target"])
        if src_idx is not None and tgt_idx is not None:
            echart_edges.append({
                "source": str(src_idx),
                "target": str(tgt_idx),
                "label": {
                    "show": not mini,
                    "formatter": edge.get("relation", ""),
                    "fontSize": 9,
                    "color": theme.TEXT_MUTED,
                },
                "lineStyle": {
                    "color": theme.BORDER,
                    "curveness": 0.1,
                },
            })

    echart_categories = [{"name": c["name"]} for c in categories[:15]]
    if not echart_categories:
        echart_categories = [{"name": "general"}]

    option = {
        "backgroundColor": "transparent",
        "tooltip": {
            "trigger": "item",
            "formatter": "{b}<br/>{c}",
            "backgroundColor": theme.CARD_BG,
            "borderColor": theme.BORDER,
            "textStyle": {"color": theme.TEXT},
        },
        "legend": {
            "show": not mini,
            "data": [c["name"] for c in echart_categories],
            "textStyle": {"color": theme.TEXT_MUTED, "fontSize": 10},
            "type": "scroll",
            "bottom": 0,
        },
        "series": [{
            "type": "graph",
            "layout": "force",
            "roam": True,
            "draggable": True,
            "data": echart_nodes,
            "links": echart_edges,
            "categories": echart_categories,
            "label": {
                "show": True,
                "position": "right",
                "fontSize": 11 if not mini else 10,
                "color": theme.TEXT,
            },
            "force": {
                "repulsion": 200 if not mini else 120,
                "gravity": 0.1,
                "edgeLength": [80, 200] if not mini else [50, 120],
                "layoutAnimation": True,
            },
            "lineStyle": {
                "opacity": 0.6,
                "width": 1.5,
            },
            "emphasis": {
                "focus": "adjacency",
                "lineStyle": {"width": 3},
            },
        }],
    }

    ui.echart(option).classes(f"w-full").style(f"height: {height}")

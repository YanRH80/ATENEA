"""
atenea/web/pages/dashboard.py — Single-page command center

Design: Anki deck-browser density + Brainscape mastery bars.
One screen = entire state of every project + what to do next.
"""

from nicegui import ui

from atenea.web import theme
from atenea.web.components.header import render_header
from atenea.services.project_service import list_projects_with_stats
from atenea import __version__, __version_date__


def render():
    """Render the dashboard."""
    render_header()

    projects = list_projects_with_stats()

    with ui.column().classes("w-full max-w-5xl mx-auto px-4 py-6 gap-0"):

        if not projects:
            _render_empty()
            return

        # ── Project cards ──────────────────────────────────────
        for p in projects:
            _render_project_row(p)

        # ── Footer: about + methodology (inline, not a page) ──
        _render_footer()


# ============================================================
# PROJECT ROW — dense, Anki-style
# ============================================================

def _render_project_row(p):
    """One project = one dense card with everything visible."""
    name = p["name"]

    with ui.card().classes(
        "bg-slate-800/60 w-full mb-3 border border-slate-700/50"
    ).style("padding: 16px"):

        # Row 1: Name + pipeline + actions
        with ui.row().classes("w-full items-center gap-4"):
            # Project name
            ui.label(name.upper()).classes(
                "text-lg font-bold text-blue-400 min-w-[120px]"
            )

            # Pipeline badges (compact: ● = done, ○ = pending)
            with ui.row().classes("gap-1 items-center"):
                _pipeline_dot("Sync", p["n_sources"] > 0, f"{p['n_sources']} docs")
                ui.label("→").classes("text-slate-600 text-xs")
                _pipeline_dot("Study", p["has_knowledge"], f"{p['n_knowledge']} conceptos")
                ui.label("→").classes("text-slate-600 text-xs")
                _pipeline_dot("Generate", p["has_questions"], f"{p['n_questions']} preguntas")
                ui.label("→").classes("text-slate-600 text-xs")
                _pipeline_dot("Test", p["has_coverage"], f"{p['known']}/{p['total']} dominados" if p['total'] > 0 else "sin test")

            ui.space()

            # Action buttons
            if p["has_questions"]:
                ui.button(
                    "TEST",
                    on_click=lambda _, n=name: ui.navigate.to(f"/test/{n}"),
                ).props("flat dense color=primary").classes("text-xs px-3")

            if p["has_knowledge"] or p["has_coverage"]:
                ui.button(
                    "ANÁLISIS",
                    on_click=lambda _, n=name: ui.navigate.to(f"/analysis/{n}"),
                ).props("flat dense color=grey-5").classes("text-xs px-3")

        # Row 2: Mastery bar + stats
        with ui.row().classes("w-full items-center gap-4 mt-3"):
            # Mastery bar (Brainscape-style: colored segments)
            _mastery_bar(p)

            # Score
            if p["coverage_pct"] is not None:
                pct = p["coverage_pct"]
                color = theme.KNOWN if pct >= 70 else theme.TESTING if pct >= 40 else theme.UNKNOWN
                ui.label(f"{pct}%").classes("text-xl font-bold min-w-[50px] text-right").style(f"color: {color}")
            else:
                ui.label("—").classes("text-xl font-bold text-slate-600 min-w-[50px] text-right")

        # Row 3: Next step suggestion (inline, subtle)
        _next_step(p, name)


def _pipeline_dot(label, done, detail):
    """Compact pipeline status indicator."""
    if done:
        with ui.row().classes("items-center gap-1"):
            ui.label("●").classes("text-green-400 text-xs")
            ui.label(detail).classes("text-xs text-slate-400")
    else:
        with ui.row().classes("items-center gap-1"):
            ui.label("○").classes("text-slate-600 text-xs")
            ui.label(label).classes("text-xs text-slate-600")


def _mastery_bar(p):
    """Brainscape-style colored mastery bar."""
    total = p.get("total", 0)
    known = p.get("known", 0)

    if total == 0:
        # No data — grey bar
        theme.html('<div class="mastery-bar w-full"><div class="unknown" style="width:100%"></div></div>').classes("flex-1")
        return

    # Get more granular data if possible
    known_pct = known / total * 100
    # Estimate testing from remaining (we don't have exact in list_projects_with_stats)
    # For now: known = green, rest = red-ish
    testing_pct = 0  # Will be populated from compute_coverage in analysis view
    unknown_pct = 100 - known_pct - testing_pct

    theme.html(f'''
        <div class="mastery-bar w-full" title="{known}/{total} dominados">
            <div class="known" style="width:{known_pct}%"></div>
            <div class="testing" style="width:{testing_pct}%"></div>
            <div class="unknown" style="width:{unknown_pct}%"></div>
        </div>
    ''').classes("flex-1")


def _next_step(p, name):
    """Inline next-step suggestion."""
    if p["n_sources"] == 0:
        msg = "→ Sincroniza documentos desde Zotero (CLI: atenea)"
        color = "slate-500"
    elif not p["has_knowledge"]:
        msg = "→ Extrae conocimiento (CLI: atenea → Study)"
        color = "slate-500"
    elif not p["has_questions"]:
        msg = "→ Genera preguntas (CLI: atenea → Generate)"
        color = "slate-500"
    elif not p["has_coverage"]:
        msg = f"→ {p['n_questions']} preguntas listas — inicia un test"
        color = "blue-400"
    else:
        pending = p["total"] - p["known"]
        if pending > 0:
            msg = f"→ {pending} conceptos por repasar"
            color = "yellow-400"
        else:
            msg = "→ Dominio completo"
            color = "green-400"

    ui.label(msg).classes(f"text-xs text-{color} mt-2")


# ============================================================
# EMPTY STATE
# ============================================================

def _render_empty():
    """No projects yet."""
    with ui.column().classes("items-center py-16 gap-4"):
        ui.label("ATENEA").classes("text-4xl font-bold text-blue-400")
        ui.label("Adaptive learning from medical documents").classes("text-slate-400")
        ui.label("No hay proyectos. Crea uno desde la CLI:").classes("text-slate-500 mt-4")
        ui.label("$ atenea").classes("font-mono text-blue-300 bg-slate-800 px-4 py-2 rounded")


# ============================================================
# FOOTER — methodology inline (no separate about page)
# ============================================================

def _render_footer():
    """Collapsible methodology + transparency section."""
    with ui.expansion(
        "Acerca de ATENEA",
        icon="info_outline",
    ).classes("w-full mt-8 text-slate-400").props("dense header-class=text-slate-500"):

        with ui.column().classes("gap-3 text-xs text-slate-500 py-2"):
            theme.html(f"""
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">
                    <div>
                        <div style="color:{theme.TEXT_MUTED}; font-weight:600; margin-bottom:4px;">Qué hace</div>
                        <div>• Extrae entidades y relaciones de textos médicos</div>
                        <div>• Genera preguntas tipo MIR/ENARM (5 opciones, justificación verbatim)</div>
                        <div>• Programa revisiones con repetición espaciada (SM-2)</div>
                        <div>• Visualiza grafo de conocimiento con cobertura por concepto</div>
                    </div>
                    <div>
                        <div style="color:{theme.TEXT_MUTED}; font-weight:600; margin-bottom:4px;">Qué NO hace</div>
                        <div>• No genera conocimiento nuevo — solo estructura lo del texto</div>
                        <div>• No reemplaza la lectura crítica del material original</div>
                        <div>• No garantiza cobertura completa del documento</div>
                        <div>• No es sustituto del criterio clínico</div>
                    </div>
                    <div>
                        <div style="color:{theme.TEXT_MUTED}; font-weight:600; margin-bottom:4px;">Fundamentos</div>
                        <div>• Repetición espaciada: SM-2 (Wozniak, 1990)</div>
                        <div>• Extracción: prompt engineering + citas verbatim como ground truth</div>
                        <div>• Evidencia: clasificación SIGN/NICE (1++ a 4, grado A-D)</div>
                        <div>• Capacidad de memoria: regla 7±2 (Miller, 1956)</div>
                    </div>
                    <div>
                        <div style="color:{theme.TEXT_MUTED}; font-weight:600; margin-bottom:4px;">Transparencia</div>
                        <div>• Cada relación incluye cita textual verificable</div>
                        <div>• Justificaciones con referencia [citekey, p.X]</div>
                        <div>• Status basado en datos: ratio aciertos + revisiones</div>
                        <div>• v{__version__} ({__version_date__}) · Datos locales · Sin telemetría</div>
                    </div>
                </div>
            """)

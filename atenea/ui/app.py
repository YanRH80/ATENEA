"""
atenea/ui/app.py — Developer Dashboard (NiceGUI)

A developer-focused UI to visualize pipeline internals, monitor progress,
inspect data structures, and understand optimization opportunities.

Launch: atenea ui [--port 8080]
   or: python -m atenea.ui.app

Phase 2 UI Overhaul:
- Project cards as folder-based workspaces
- Inline expandable logs per pipeline step
- Progress bars with %/runtime/ETA
- MC question generation support
"""

import asyncio
import json
import os
import time
import threading
from pathlib import Path

from nicegui import ui, app, run
from nicegui.events import UploadEventArguments

from dotenv import load_dotenv
load_dotenv()

from atenea import storage
from config import defaults, models as models_config


# ============================================================
# GLOBAL STATE
# ============================================================

class State:
    """Mutable state shared across UI components."""
    current_project = None
    pipeline_running = False
    pipeline_timings = {}  # step_name -> seconds


state = State()

# Color palette
COLORS = {
    "bg": "#0f1117",
    "card": "#1a1d27",
    "card_hover": "#1f2335",
    "accent": "#6366f1",
    "accent2": "#8b5cf6",
    "green": "#22c55e",
    "yellow": "#eab308",
    "red": "#ef4444",
    "dim": "#6b7280",
    "text": "#e5e7eb",
    "border": "#2d3348",
}

STEP_DEFS = [
    ("convert", "PDF → Markdown", "description", "Convert PDF to markdown text using OCR"),
    ("chunk", "Markdown → Chunks", "grid_view", "Split markdown into structured sections, lines, keywords"),
    ("extract", "Extract CSPOJ (AI)", "psychology", "Extract points, paths, sets, maps with graph enrichment"),
    ("generate", "Generate Questions", "help_outline", "Generate questions from CSPOJ knowledge structures"),
]


# ============================================================
# LAYOUT
# ============================================================

def create_header():
    """Top navigation bar."""
    with ui.header().classes("items-center justify-between px-6 py-2").style(
        f"background: {COLORS['card']}; border-bottom: 1px solid {COLORS['border']}"
    ):
        ui.label("ATENEA").classes("text-xl font-bold").style(
            f"color: {COLORS['accent']}; letter-spacing: 2px"
        )
        with ui.row().classes("gap-1"):
            ui.button("Pipeline", icon="play_circle",
                      on_click=lambda: ui.navigate.to("/")).props("flat color=white size=sm")
            ui.button("Inspector", icon="search",
                      on_click=lambda: ui.navigate.to("/inspector")).props("flat color=white size=sm")
            ui.button("Graph", icon="hub",
                      on_click=lambda: ui.navigate.to("/graph")).props("flat color=white size=sm")
            ui.button("Test", icon="quiz",
                      on_click=lambda: ui.navigate.to("/test")).props("flat color=white size=sm")
            ui.button("Analytics", icon="insights",
                      on_click=lambda: ui.navigate.to("/analytics")).props("flat color=white size=sm")
            ui.button("Optimizer", icon="speed",
                      on_click=lambda: ui.navigate.to("/optimizer")).props("flat color=white size=sm")


def _format_time(seconds):
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _format_eta(elapsed, fraction):
    """Estimate remaining time from elapsed and fraction done."""
    if fraction <= 0 or elapsed <= 0:
        return "..."
    total_est = elapsed / fraction
    remaining = total_est - elapsed
    return f"~{_format_time(remaining)}"


# ============================================================
# PAGE: PIPELINE (main)
# ============================================================

@ui.page("/")
def page_pipeline():
    create_header()

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        ui.label("Pipeline Runner").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")

        # --- Project Cards ---
        with ui.row().classes("w-full gap-4 flex-wrap") as project_cards_row:
            _render_project_cards(project_cards_row)

        # --- New project / upload ---
        with ui.card().classes("w-full p-4").style(
            f"background: {COLORS['card']}; border: 1px dashed {COLORS['border']}"
        ):
            with ui.row().classes("w-full items-end gap-4"):
                new_project_input = ui.input(
                    "New project name", placeholder="e.g. biologia-101"
                ).classes("w-48")
                pdf_upload = ui.upload(
                    label="Drop PDF here",
                    auto_upload=True,
                    on_upload=lambda e: handle_pdf_upload(e, new_project_input),
                ).classes("w-64").props('accept=".pdf"')
                ui.label("Upload a PDF to create a new project or add to an existing one").style(
                    f"color: {COLORS['dim']}; font-size: 12px"
                )

        # --- Pipeline Execution Panel ---
        with ui.card().classes("w-full p-4").style(f"background: {COLORS['card']}"):
            with ui.row().classes("w-full items-center justify-between mb-3"):
                ui.label("Pipeline Steps").classes("text-lg font-semibold").style(f"color: {COLORS['text']}")
                with ui.row().classes("items-end gap-2"):
                    project_select = ui.select(
                        options=storage.list_projects() or ["(none)"],
                        label="Project",
                        value=(storage.list_projects() or [None])[0],
                    ).classes("w-40")
                    gen_mode = ui.select(
                        options=["lite (free-text)", "MC (AI)", "full (all types)"],
                        label="Generate mode",
                        value="lite (free-text)",
                    ).classes("w-40")

            # Per-step panels with inline logs
            step_panels = {}
            for step_name, step_label, step_icon, step_desc in STEP_DEFS:
                step_panels[step_name] = _create_step_panel(step_name, step_label, step_icon, step_desc)

        # Run buttons
        with ui.row().classes("gap-3"):
            run_btn = ui.button(
                "Run Full Pipeline", icon="play_arrow",
                on_click=lambda: _on_run_pipeline(
                    project_select.value, step_panels, run_btn, gen_mode.value,
                ),
            ).props("color=indigo unelevated").classes("px-6")

            ui.button(
                "Extract Only", icon="psychology",
                on_click=lambda: _on_run_single(
                    "extract", project_select.value, step_panels,
                ),
            ).props("outline color=purple").classes("px-4")

            ui.button(
                "Generate Only", icon="help_outline",
                on_click=lambda: _on_run_single(
                    "generate", project_select.value, step_panels, gen_mode.value,
                ),
            ).props("outline color=purple").classes("px-4")


def _render_project_cards(container):
    """Render project cards as folder-like workspaces."""
    projects = storage.list_projects()
    if not projects:
        with container:
            with ui.card().classes("p-6").style(
                f"background: {COLORS['card']}; border: 1px dashed {COLORS['border']}"
            ):
                ui.icon("folder_open").classes("text-4xl").style(f"color: {COLORS['dim']}")
                ui.label("No projects yet").style(f"color: {COLORS['dim']}")
                ui.label("Upload a PDF below to get started").style(f"color: {COLORS['dim']}; font-size: 12px")
        return

    with container:
        for p in projects:
            sources = storage.list_sources(p)
            has_data = os.path.exists(storage.get_project_path(p, "data.json"))
            has_questions = os.path.exists(storage.get_project_path(p, "preguntas.json"))

            # Determine status
            if has_questions:
                status_text, status_color, status_icon = "ready", COLORS["green"], "check_circle"
            elif has_data:
                status_text, status_color, status_icon = "extracted", COLORS["yellow"], "psychology"
            elif sources:
                status_text, status_color, status_icon = "converted", COLORS["accent"], "description"
            else:
                status_text, status_color, status_icon = "empty", COLORS["dim"], "folder"

            with ui.card().classes("p-4 cursor-pointer").style(
                f"background: {COLORS['card']}; border: 1px solid {COLORS['border']}; "
                f"min-width: 200px; transition: all 0.2s"
            ).on("mouseenter", lambda e, c=COLORS['card_hover']: None):
                with ui.row().classes("items-center gap-2 mb-2"):
                    ui.icon("folder").classes("text-2xl").style(f"color: {COLORS['accent']}")
                    ui.label(p).classes("text-lg font-semibold").style(f"color: {COLORS['text']}")
                with ui.row().classes("gap-3 items-center"):
                    ui.badge(f"{len(sources)} PDF{'s' if len(sources) != 1 else ''}").props("outline")
                    with ui.row().classes("items-center gap-1"):
                        ui.icon(status_icon).style(f"color: {status_color}; font-size: 14px")
                        ui.label(status_text).style(f"color: {status_color}; font-size: 12px")

                # Show question count if available
                if has_questions:
                    preguntas = storage.load_json(storage.get_project_path(p, "preguntas.json"))
                    n_q = len((preguntas or {}).get("questions", []))
                    by_type = (preguntas or {}).get("stats", {}).get("by_type", {})
                    type_str = ", ".join(f"{k}: {v}" for k, v in by_type.items())
                    ui.label(f"{n_q} questions" + (f" ({type_str})" if type_str else "")).style(
                        f"color: {COLORS['dim']}; font-size: 11px; margin-top: 4px"
                    )


def _create_step_panel(step_name, step_label, step_icon, step_desc):
    """Create an expandable step panel with inline log, progress, and timing."""
    with ui.expansion(
        text=f"  {step_label}",
        icon=step_icon,
        value=False,
    ).classes("w-full").style(
        f"background: #1e2132; border-radius: 8px; margin-bottom: 4px"
    ) as expansion:
        # Progress bar row
        with ui.row().classes("w-full items-center gap-3 px-2"):
            progress_bar = ui.linear_progress(value=0, show_value=False).classes("flex-grow")
            progress_bar.style("height: 6px")
            pct_label = ui.label("").classes("text-xs font-mono").style(
                f"color: {COLORS['dim']}; min-width: 40px; text-align: right"
            )
            time_label = ui.label("").classes("text-xs font-mono").style(
                f"color: {COLORS['dim']}; min-width: 80px; text-align: right"
            )
            eta_label = ui.label("").classes("text-xs font-mono").style(
                f"color: {COLORS['dim']}; min-width: 70px; text-align: right"
            )

        # Description
        ui.label(step_desc).style(f"color: {COLORS['dim']}; font-size: 11px; padding: 0 8px")

        # Inline log
        log_area = ui.log(max_lines=100).classes("w-full h-32").style(
            "font-family: 'JetBrains Mono', monospace; font-size: 11px; "
            f"background: {COLORS['bg']}; color: {COLORS['text']}; margin-top: 4px"
        )

        # Stats summary (shown after completion)
        stats_label = ui.label("").classes("text-xs px-2 py-1").style(f"color: {COLORS['green']}")

    return {
        "expansion": expansion,
        "progress": progress_bar,
        "pct_label": pct_label,
        "time_label": time_label,
        "eta_label": eta_label,
        "log": log_area,
        "stats_label": stats_label,
        "start_time": None,
    }


async def handle_pdf_upload(e: UploadEventArguments, name_input):
    """Handle PDF file upload."""
    content = e.content.read()
    project = name_input.value or "uploaded"

    # Save to temp
    tmp_path = Path(f"/tmp/atenea_upload_{e.name}")
    tmp_path.write_bytes(content)

    name_input.value = project
    ui.notify(f"PDF ready: {e.name} ({len(content):,} bytes)", type="positive")


# ============================================================
# PIPELINE EXECUTION
# ============================================================

async def _on_run_pipeline(project_name, step_panels, run_btn, gen_mode):
    """Run the full pipeline with live UI updates."""
    if not project_name or project_name == "(none)":
        ui.notify("Select or create a project first", type="warning")
        return

    if state.pipeline_running:
        ui.notify("Pipeline already running", type="warning")
        return

    state.pipeline_running = True
    run_btn.disable()
    state.pipeline_timings = {}

    # Reset all panels
    for name, panel in step_panels.items():
        _reset_step_panel(panel)

    # Check for uploaded PDF
    uploads = list(Path("/tmp").glob("atenea_upload_*.pdf"))
    pdf_path = str(uploads[0]) if uploads else None

    steps = []
    if pdf_path:
        steps.append(("convert", pdf_path, project_name))
    steps.append(("chunk", project_name, None))
    steps.append(("extract", project_name, None))
    steps.append(("generate", project_name, gen_mode))

    success = True
    for step_name, arg1, arg2 in steps:
        panel = step_panels.get(step_name)
        if not panel:
            continue
        ok = await _run_step(step_name, arg1, arg2, panel)
        if not ok:
            success = False
            break

    state.pipeline_running = False
    run_btn.enable()

    if success:
        ui.notify("Pipeline complete!", type="positive", position="top", timeout=5000)
    else:
        ui.notify("Pipeline failed — check logs", type="negative", position="top")


async def _on_run_single(step_name, project_name, step_panels, gen_mode=None):
    """Run a single pipeline step."""
    if not project_name or project_name == "(none)":
        ui.notify("Select a project first", type="warning")
        return

    panel = step_panels.get(step_name)
    if not panel:
        return

    _reset_step_panel(panel)
    arg2 = gen_mode if step_name == "generate" else None
    await _run_step(step_name, project_name, arg2, panel)


def _reset_step_panel(panel):
    """Reset a step panel to initial state."""
    panel["progress"].set_value(0)
    panel["pct_label"].text = ""
    panel["time_label"].text = ""
    panel["eta_label"].text = ""
    panel["stats_label"].text = ""
    panel["log"].clear()
    panel["start_time"] = None
    # Set expansion header back to default color
    panel["expansion"].style(
        f"background: #1e2132; border-radius: 8px; margin-bottom: 4px"
    )


def _update_step_progress(panel, fraction, msg=""):
    """Update progress bar, percentage, timing, and ETA for a step."""
    panel["progress"].set_value(min(fraction, 1.0))
    panel["pct_label"].text = f"{fraction * 100:.0f}%"

    if panel["start_time"]:
        elapsed = time.time() - panel["start_time"]
        panel["time_label"].text = _format_time(elapsed)
        if fraction > 0:
            panel["eta_label"].text = _format_eta(elapsed, fraction)

    if msg:
        panel["log"].push(f"  {msg}")


async def _run_step(step_name, arg1, arg2, panel):
    """Execute a single pipeline step with progress tracking."""
    # Open the expansion panel
    panel["expansion"].set_value(True)
    panel["start_time"] = time.time()
    panel["log"].push(f"{'=' * 50}")
    panel["log"].push(f"  {step_name.upper()} starting...")
    panel["log"].push(f"{'=' * 50}")

    # Running indicator
    panel["expansion"].style(
        f"background: #1e2132; border-left: 3px solid {COLORS['yellow']}; "
        f"border-radius: 8px; margin-bottom: 4px"
    )

    try:
        result = await run.io_bound(
            lambda: _execute_step(step_name, arg1, arg2, panel)
        )
        elapsed = time.time() - panel["start_time"]
        state.pipeline_timings[step_name] = elapsed

        # Success state
        panel["progress"].set_value(1.0)
        panel["pct_label"].text = "100%"
        panel["time_label"].text = _format_time(elapsed)
        panel["eta_label"].text = ""
        panel["expansion"].style(
            f"background: #1e2132; border-left: 3px solid {COLORS['green']}; "
            f"border-radius: 8px; margin-bottom: 4px"
        )
        panel["log"].push(f"\n  Done in {_format_time(elapsed)}")

        # Collapse after success (keep open if user expanded manually)
        panel["expansion"].set_value(False)
        return True

    except Exception as e:
        elapsed = time.time() - panel["start_time"]
        state.pipeline_timings[step_name] = elapsed

        panel["expansion"].style(
            f"background: #1e2132; border-left: 3px solid {COLORS['red']}; "
            f"border-radius: 8px; margin-bottom: 4px"
        )
        panel["time_label"].text = f"{_format_time(elapsed)} FAILED"
        panel["log"].push(f"\n  ERROR: {e}")
        ui.notify(f"{step_name} failed: {e}", type="negative")
        return False


def _execute_step(step_name, arg1, arg2, panel):
    """Execute a pipeline step (runs in thread)."""
    if step_name == "convert":
        from atenea.convert import convert_pdf_to_markdown
        pdf_path, project = arg1, arg2
        panel["log"].push(f"  Converting: {Path(pdf_path).name}")
        _update_step_progress(panel, 0.1, f"Loading Marker models...")
        result = convert_pdf_to_markdown(pdf_path, project)
        _update_step_progress(panel, 0.9, f"Saved: {result}")
        panel["stats_label"].text = f"Output: {result}"
        return result

    elif step_name == "chunk":
        from atenea.chunk import chunk_markdown, split_into_sections, extract_lines, extract_keywords
        from atenea.chunk import load_markdown
        project = arg1

        md_text, source_id = load_markdown(project)
        panel["log"].push(f"  Loaded: {len(md_text):,} chars from {source_id}")
        _update_step_progress(panel, 0.1, f"Splitting sections...")

        sections = split_into_sections(md_text)
        panel["log"].push(f"  Sections: {len(sections)}")
        _update_step_progress(panel, 0.3, f"{len(sections)} sections")

        lines = extract_lines(md_text, sections)
        panel["log"].push(f"  Lines: {len(lines)}")
        _update_step_progress(panel, 0.6, f"{len(lines)} lines")

        keywords = extract_keywords(lines)
        panel["log"].push(f"  Keywords: {len(keywords)}")
        _update_step_progress(panel, 0.8, f"{len(keywords)} keywords")

        result = chunk_markdown(project)
        panel["stats_label"].text = f"{len(sections)}s / {len(lines)}l / {len(keywords)}kw"
        return result

    elif step_name == "extract":
        from atenea.extract import run_extraction
        project = arg1

        def extraction_progress(current, total, msg):
            fraction = current / max(total, 1)
            _update_step_progress(panel, fraction, msg)

        panel["log"].push(f"  Running full extraction with graph enrichment...")
        _update_step_progress(panel, 0.0, "Starting extraction pipeline...")

        result = run_extraction(project, progress_callback=extraction_progress)

        # Show summary stats
        n_pts = len(result.get("points", []))
        n_paths = len(result.get("paths", []))
        n_sets = len(result.get("sets", []))
        n_maps = len(result.get("maps", []))
        n_edges = len(result.get("graph_edges", []))

        panel["log"].push(f"\n  === Extraction Summary ===")
        panel["log"].push(f"  Points:  {n_pts}")
        panel["log"].push(f"  Paths:   {n_paths}")
        panel["log"].push(f"  Sets:    {n_sets}")
        panel["log"].push(f"  Maps:    {n_maps}")
        panel["log"].push(f"  Edges:   {n_edges}")

        # Show extraction confidence metrics
        ext_stats = result.get("extraction_stats", {})
        if ext_stats:
            panel["log"].push(f"\n  === Confidence Metrics ===")
            for name, metric in ext_stats.items():
                if isinstance(metric, dict) and "value" in metric:
                    val = metric["value"]
                    target = metric.get("target", "")
                    status = metric.get("status", "")
                    flag = "OK" if status == "good" else "LOW"
                    panel["log"].push(f"  {name}: {val:.1%} (target: {target}) [{flag}]")

        panel["stats_label"].text = (
            f"{n_pts}pt / {n_paths}pa / {n_sets}s / {n_maps}m / {n_edges}edges"
        )
        return result

    elif step_name == "generate":
        project = arg1
        gen_mode = arg2 or "lite (free-text)"

        def gen_progress(current, total, msg):
            fraction = current / max(total, 1)
            _update_step_progress(panel, fraction, msg)

        if "MC" in gen_mode:
            from atenea.generate import generate_questions, Q_MULTIPLE_CHOICE
            panel["log"].push(f"  Generating MC questions (AI)...")
            _update_step_progress(panel, 0.0, "Starting MC generation...")
            result = generate_questions(
                project, question_types=[Q_MULTIPLE_CHOICE],
                progress_callback=gen_progress,
            )
        elif "full" in gen_mode:
            from atenea.generate import generate_questions
            panel["log"].push(f"  Generating all question types (AI)...")
            _update_step_progress(panel, 0.0, "Starting full generation...")
            result = generate_questions(project, progress_callback=gen_progress)
        else:
            from atenea.generate import generate_questions_lite
            panel["log"].push(f"  Generating free-text questions (no LLM)...")
            _update_step_progress(panel, 0.0, "Starting lite generation...")
            result = generate_questions_lite(project, max_paths=999, progress_callback=gen_progress)

        n = len(result.get("questions", []))
        by_type = result.get("stats", {}).get("by_type", {})
        type_str = ", ".join(f"{k}: {v}" for k, v in by_type.items())

        panel["log"].push(f"\n  Total: {n} questions")
        if type_str:
            panel["log"].push(f"  Types: {type_str}")

        panel["stats_label"].text = f"{n} questions ({type_str})" if type_str else f"{n} questions"
        return result


# ============================================================
# PAGE: DATA INSPECTOR
# ============================================================

@ui.page("/inspector")
def page_inspector():
    create_header()

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        ui.label("Data Inspector").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")

        projects = storage.list_projects()
        if not projects:
            ui.label("No projects yet. Run the pipeline first.").style(f"color: {COLORS['dim']}")
            return

        project_select = ui.select(
            options=projects, label="Project", value=projects[0],
            on_change=lambda e: load_inspector_data(e.value, tabs_container),
        ).classes("w-48")

        tabs_container = ui.column().classes("w-full")
        load_inspector_data(projects[0], tabs_container)


def load_inspector_data(project, container):
    """Load and display all data for a project."""
    container.clear()

    sources = storage.list_sources(project)
    source_id = sources[-1] if sources else None

    with container:
        with ui.tabs().classes("w-full") as tabs:
            tab_md = ui.tab("clean-md.json")
            tab_data = ui.tab("data.json")
            tab_preguntas = ui.tab("preguntas.json")
            tab_raw = ui.tab("Raw JSON")

        with ui.tab_panels(tabs, value=tab_data).classes("w-full"):
            with ui.tab_panel(tab_md):
                _render_clean_md(project, source_id)
            with ui.tab_panel(tab_data):
                _render_data_json(project, source_id)
            with ui.tab_panel(tab_preguntas):
                _render_preguntas(project, source_id)
            with ui.tab_panel(tab_raw):
                _render_raw_json(project, source_id)


def _render_clean_md(project, source_id):
    """Render clean-md.json contents."""
    if not source_id:
        ui.label("No source data").style(f"color: {COLORS['dim']}")
        return

    path = storage.get_source_path(project, source_id, "clean-md.json")
    data = storage.load_json(path)
    if not data:
        ui.label("clean-md.json not found").style(f"color: {COLORS['dim']}")
        return

    stats = data.get("stats", {})
    with ui.row().classes("gap-4 mb-4"):
        for label, value in stats.items():
            with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
                ui.label(str(value)).classes("text-2xl font-bold").style(f"color: {COLORS['accent']}")
                ui.label(label.replace("total_", "")).style(f"color: {COLORS['dim']}; font-size: 12px")

    ui.label("Section Hierarchy").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
    sections = data.get("sections", [])
    for s in sections:
        indent = "  " * (s["level"] - 1)
        lines_range = f"L{s['start_line']}-{s['end_line']}"
        with ui.row().classes("items-center gap-2"):
            ui.label(f"{indent}{'#' * s['level']}").style(f"color: {COLORS['accent']}; font-family: monospace")
            ui.label(s["title"]).style(f"color: {COLORS['text']}")
            ui.badge(lines_range).props("outline")

    ui.label("Top Keywords").classes("text-lg font-semibold mt-4 mb-2").style(f"color: {COLORS['text']}")
    keywords = data.get("keywords", [])[:50]
    with ui.row().classes("flex-wrap gap-1"):
        for i, kw in enumerate(keywords):
            size = max(10, 18 - i // 5)
            ui.label(kw).style(
                f"font-size: {size}px; color: {COLORS['accent'] if i < 10 else COLORS['text']}; "
                f"opacity: {max(0.4, 1 - i * 0.015)}"
            )


def _render_data_json(project, source_id):
    """Render data.json (CSPOJ structures)."""
    if not source_id:
        return

    path = storage.get_source_path(project, source_id, "data.json")
    data = storage.load_json(path)
    if not data:
        ui.label("data.json not found — run extract first").style(f"color: {COLORS['dim']}")
        return

    stats = data.get("stats", {})
    with ui.row().classes("gap-4 mb-4"):
        for label, value in stats.items():
            with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
                ui.label(str(value)).classes("text-2xl font-bold").style(f"color: {COLORS['accent']}")
                ui.label(label.replace("total_", "")).style(f"color: {COLORS['dim']}; font-size: 12px")

    # Extraction confidence metrics
    ext_stats = data.get("extraction_stats", {})
    if ext_stats:
        ui.label("Extraction Confidence").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
        with ui.row().classes("gap-3 mb-4 flex-wrap"):
            for metric_name, metric in ext_stats.items():
                if not isinstance(metric, dict):
                    continue
                val = metric.get("value", 0)
                target = metric.get("target", None)
                status = metric.get("status", "")
                color = COLORS["green"] if status == "good" else COLORS["yellow"]

                with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
                    ui.label(f"{val:.0%}" if isinstance(val, float) and val <= 1 else str(val)).classes(
                        "text-xl font-bold"
                    ).style(f"color: {color}")
                    ui.label(metric_name.replace("_", " ")).style(f"color: {COLORS['dim']}; font-size: 11px")
                    if target:
                        ui.label(f"target: {target}").style(f"color: {COLORS['dim']}; font-size: 10px")

    # Graph stats
    graph_stats = data.get("graph_stats", {})
    if graph_stats:
        ui.label("Graph Connectivity").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
        with ui.row().classes("gap-4 mb-4"):
            point_dist = graph_stats.get("point_distribution", {})
            for k, v in point_dist.items():
                with ui.card().classes("p-2").style(f"background: #22253a"):
                    ui.label(str(v)).classes("text-lg font-bold").style(f"color: {COLORS['accent2']}")
                    ui.label(f"points: {k}").style(f"color: {COLORS['dim']}; font-size: 10px")

            path_cov = graph_stats.get("path_coverage", {})
            for k, v in path_cov.items():
                with ui.card().classes("p-2").style(f"background: #22253a"):
                    ui.label(str(v)).classes("text-lg font-bold").style(f"color: {COLORS['accent']}")
                    ui.label(f"paths: {k}").style(f"color: {COLORS['dim']}; font-size: 10px")

    # CSPOJ Paths table
    ui.label("CSPOJ Paths").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
    paths = data.get("paths", [])

    columns = [
        {"name": "context", "label": "Context", "field": "context", "align": "left"},
        {"name": "subject", "label": "Subject", "field": "subject", "align": "left"},
        {"name": "predicate", "label": "Predicate", "field": "predicate", "align": "left"},
        {"name": "object", "label": "Object", "field": "object", "align": "left"},
        {"name": "pts", "label": "Pts", "field": "pts", "align": "center"},
        {"name": "maps", "label": "Maps", "field": "maps", "align": "center"},
    ]
    rows = [
        {
            "context": p["context"][:40],
            "subject": p["subject"][:30],
            "predicate": p["predicate"][:25],
            "object": p["object"][:30],
            "pts": len(p.get("point_ids", [])),
            "maps": len(p.get("map_ids", [])),
        }
        for p in paths[:50]
    ]
    ui.table(columns=columns, rows=rows, row_key="subject").classes("w-full").style(
        f"background: {COLORS['bg']}"
    )

    # Sets
    ui.label("Semantic Sets").classes("text-lg font-semibold mt-4 mb-2").style(f"color: {COLORS['text']}")
    sets = data.get("sets", [])
    for s in sets:
        n_covering = len(s.get("covering_paths", []))
        with ui.expansion(
            f"{s['name']} ({len(s.get('point_ids', []))} points, {n_covering} paths)"
        ).classes("w-full"):
            ui.label(s.get("description", "")).style(f"color: {COLORS['dim']}")


def _render_preguntas(project, source_id):
    """Render preguntas.json."""
    path = storage.get_project_path(project, "preguntas.json")
    data = storage.load_json(path)
    if not data:
        ui.label("No questions generated yet").style(f"color: {COLORS['dim']}")
        return

    questions = data.get("questions", [])
    stats = data.get("stats", {})

    with ui.row().classes("gap-4 mb-4"):
        with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
            ui.label(str(stats.get("total", 0))).classes("text-2xl font-bold").style(f"color: {COLORS['accent']}")
            ui.label("total questions").style(f"color: {COLORS['dim']}; font-size: 12px")

        by_type = stats.get("by_type", {})
        for qtype, count in by_type.items():
            with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
                ui.label(str(count)).classes("text-xl font-bold").style(f"color: {COLORS['accent2']}")
                ui.label(qtype).style(f"color: {COLORS['dim']}; font-size: 12px")

    # Quality score distribution (for MC questions)
    mc_questions = [q for q in questions if q.get("type") == "multiple_choice"]
    if mc_questions:
        scores = [q.get("quality_score", 0) for q in mc_questions]
        avg_score = sum(scores) / len(scores) if scores else 0
        ui.label(f"MC Quality: avg {avg_score:.2f} ({len(mc_questions)} questions)").classes(
            "text-sm mb-2"
        ).style(f"color: {COLORS['text']}")

    # Sample questions
    ui.label("Sample Questions").classes("text-lg font-semibold mt-4 mb-2").style(f"color: {COLORS['text']}")
    for q in questions[:20]:
        comp = q.get("component", "?")
        diff = q.get("difficulty", 0)
        qtype = q.get("type", "?")
        diff_color = ["", COLORS["green"], COLORS["green"], COLORS["yellow"],
                      COLORS["yellow"], COLORS["red"]]
        color = diff_color[min(diff, 5)] if diff else COLORS["dim"]

        with ui.card().classes("w-full p-3 mb-1").style("background: #22253a"):
            with ui.row().classes("items-center gap-2"):
                ui.badge(qtype[:2].upper(), color="indigo").props("dense")
                ui.badge(comp, color="purple").props("outline dense")
                ui.badge(f"d={diff}").style(f"background: {color}").props("dense")
                if q.get("quality_score"):
                    ui.badge(f"q={q['quality_score']:.1f}").props("outline dense")
                ui.label(q.get("question_text", q.get("statement", ""))[:120]).style(
                    f"color: {COLORS['text']}; font-size: 13px"
                )

            # Show options for MC questions
            if qtype == "multiple_choice" and q.get("options"):
                with ui.column().classes("ml-8 mt-1 gap-0"):
                    for i, opt in enumerate(q["options"]):
                        is_correct = i == q.get("correct_index")
                        opt_color = COLORS["green"] if is_correct else COLORS["dim"]
                        prefix = ">" if is_correct else " "
                        ui.label(f"{prefix} {chr(65 + i)}. {opt[:80]}").style(
                            f"color: {opt_color}; font-size: 12px; font-family: monospace"
                        )


def _render_raw_json(project, source_id):
    """Render raw JSON files for inspection."""
    files = ["clean-md.json", "data.json", "source-meta.json", "preguntas.json"]
    for fname in files:
        if source_id:
            fpath = storage.get_source_path(project, source_id, fname)
        else:
            fpath = storage.get_project_path(project, fname)

        if not os.path.exists(fpath):
            # Try project-level
            fpath = storage.get_project_path(project, fname)

        data = storage.load_json(fpath)
        if data:
            size = os.path.getsize(fpath)
            with ui.expansion(f"{fname} ({size:,} bytes)").classes("w-full"):
                ui.code(json.dumps(data, indent=2, ensure_ascii=False)[:5000],
                        language="json").classes("w-full")


# ============================================================
# PAGE: CSPOJ KNOWLEDGE GRAPH
# ============================================================

@ui.page("/graph")
def page_graph():
    create_header()

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        ui.label("CSPOJ Knowledge Graph").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")

        projects = storage.list_projects()
        if not projects:
            ui.label("No projects yet").style(f"color: {COLORS['dim']}")
            return

        project_select = ui.select(
            options=projects, label="Project", value=projects[0],
            on_change=lambda e: render_graph(e.value, graph_container),
        ).classes("w-48")

        graph_container = ui.column().classes("w-full")
        render_graph(projects[0], graph_container)


def render_graph(project, container):
    """Render CSPOJ knowledge graph using ECharts."""
    container.clear()

    data = storage.load_json(storage.get_project_path(project, "data.json"))
    if not data:
        with container:
            ui.label("No data.json found").style(f"color: {COLORS['dim']}")
        return

    points = data.get("points", [])
    paths = data.get("paths", [])
    sets = data.get("sets", [])

    # Build graph nodes (points) and edges (paths connect points)
    nodes = []
    point_idx = {p["id"]: i for i, p in enumerate(points)}

    set_colors = [
        "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#22c55e",
        "#06b6d4", "#f43f5e", "#84cc16", "#a855f7", "#3b82f6",
        "#14b8a6", "#e11d48", "#eab308",
    ]
    point_set_color = {}
    for si, s in enumerate(sets):
        color = set_colors[si % len(set_colors)]
        for pid in s.get("point_ids", []):
            if pid not in point_set_color:
                point_set_color[pid] = color

    for i, p in enumerate(points[:150]):
        nodes.append({
            "id": str(i),
            "name": p["term"][:25],
            "symbolSize": min(8 + p.get("frequency", 1) * 2, 30),
            "itemStyle": {"color": point_set_color.get(p["id"], "#6b7280")},
            "category": 0,
        })

    edges = []
    for path in paths:
        pids = [pid for pid in path.get("point_ids", []) if pid in point_idx]
        for j in range(len(pids) - 1):
            src = point_idx.get(pids[j])
            tgt = point_idx.get(pids[j + 1])
            if src is not None and tgt is not None and src < 150 and tgt < 150:
                edges.append({
                    "source": str(src),
                    "target": str(tgt),
                    "lineStyle": {"opacity": 0.3},
                })

    with container:
        ui.label(f"{len(nodes)} nodes, {len(edges)} edges").style(f"color: {COLORS['dim']}")

        ui.echart({
            "backgroundColor": COLORS["bg"],
            "tooltip": {"trigger": "item"},
            "series": [{
                "type": "graph",
                "layout": "force",
                "data": nodes,
                "links": edges,
                "roam": True,
                "draggable": True,
                "force": {
                    "repulsion": 120,
                    "gravity": 0.1,
                    "edgeLength": [50, 200],
                    "layoutAnimation": True,
                },
                "label": {
                    "show": True,
                    "position": "right",
                    "fontSize": 10,
                    "color": COLORS["text"],
                },
                "lineStyle": {"color": "source", "curveness": 0.1},
                "emphasis": {
                    "focus": "adjacency",
                    "lineStyle": {"width": 3},
                },
            }],
        }).classes("w-full").style("height: 600px")

        ui.label("Sets").classes("text-lg font-semibold mt-4").style(f"color: {COLORS['text']}")
        with ui.row().classes("flex-wrap gap-2"):
            for si, s in enumerate(sets):
                color = set_colors[si % len(set_colors)]
                with ui.row().classes("items-center gap-1"):
                    ui.icon("circle").style(f"color: {color}; font-size: 10px")
                    ui.label(f"{s['name']} ({len(s.get('point_ids', []))})").style(
                        f"color: {COLORS['text']}; font-size: 12px"
                    )


# ============================================================
# PAGE: TEST RUNNER
# ============================================================

@ui.page("/test")
def page_test():
    create_header()

    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-6"):
        ui.label("Interactive Test").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")

        projects = storage.list_projects()
        if not projects:
            ui.label("No projects yet").style(f"color: {COLORS['dim']}")
            return

        with ui.row().classes("items-end gap-4"):
            project_select = ui.select(options=projects, label="Project", value=projects[0]).classes("w-48")
            n_questions = ui.number("Questions", value=10, min=1, max=50).classes("w-24")
            start_btn = ui.button("Start Test", icon="play_arrow").props("color=indigo")

        test_container = ui.column().classes("w-full")
        summary_container = ui.column().classes("w-full")

        start_btn.on_click(lambda: start_test(
            project_select.value, int(n_questions.value),
            test_container, summary_container, start_btn,
        ))


async def start_test(project, n, container, summary_container, start_btn):
    """Run an interactive test in the UI."""
    start_btn.disable()
    container.clear()
    summary_container.clear()

    preguntas = storage.load_json(storage.get_project_path(project, "preguntas.json"))
    if not preguntas:
        with container:
            ui.label("No questions found. Generate them first.").style(f"color: {COLORS['dim']}")
        start_btn.enable()
        return

    from atenea.test_engine import select_questions, evaluate_answer, _update_history, _save_history, _load_history
    from atenea.test_engine import _session_summary, _save_session
    from atenea.utils import generate_id

    questions = preguntas.get("questions", [])
    history = _load_history(project)
    selected = select_questions(questions, history, n=n)

    results = []
    start_time = time.time()

    for i, question in enumerate(selected):
        answer_future = asyncio.get_event_loop().create_future()

        with container:
            with ui.card().classes("w-full p-4 mb-2").style(f"background: {COLORS['card']}"):
                with ui.row().classes("items-center gap-2 mb-2"):
                    ui.badge(f"Q{i+1}/{len(selected)}").props("color=indigo")
                    ui.badge(question.get("type", "?")[:2].upper(), color="teal").props("dense")
                    ui.badge(question.get("component", "?"), color="purple").props("outline")
                    ui.badge(f"diff={question.get('difficulty', '?')}").props("outline")

                q_text = question.get("question_text", question.get("statement", ""))
                ui.label(q_text).classes("text-lg").style(f"color: {COLORS['text']}")

                # MC options
                qtype = question.get("type", "")
                if qtype == "multiple_choice" and question.get("options"):
                    with ui.column().classes("mt-2 gap-1"):
                        option_btns = []
                        for oi, opt in enumerate(question["options"]):
                            btn = ui.button(
                                f"{chr(65 + oi)}. {opt[:100]}",
                                on_click=lambda _, v=opt: (
                                    answer_future.set_result(v) if not answer_future.done() else None
                                ),
                            ).props("outline color=white align=left").classes("w-full text-left justify-start")
                            option_btns.append(btn)
                else:
                    answer_input = ui.input("Tu respuesta...").classes("w-full mt-2")
                    with ui.row().classes("gap-2 mt-2"):
                        submit_btn = ui.button("Submit", icon="send").props("color=indigo")
                        skip_btn = ui.button("Skip", icon="skip_next").props("outline color=grey")

                    def make_submit_handler(fut, inp):
                        def handler():
                            if not fut.done():
                                fut.set_result(inp.value)
                        return handler

                    def make_skip_handler(fut):
                        def handler():
                            if not fut.done():
                                fut.set_result("")
                        return handler

                    submit_btn.on_click(make_submit_handler(answer_future, answer_input))
                    answer_input.on("keydown.enter", make_submit_handler(answer_future, answer_input))
                    skip_btn.on_click(make_skip_handler(answer_future))

                feedback_label = ui.label("").classes("mt-2")

        user_answer = await answer_future
        q_elapsed_ms = 5000

        if not user_answer:
            feedback_label.text = "Skipped"
            feedback_label.style(f"color: {COLORS['dim']}")
            results.append({
                "question_id": question["id"],
                "is_correct": False, "is_partial": False,
                "score": 0.0, "quality": 0, "response_time_ms": q_elapsed_ms,
            })
            continue

        # Evaluate
        correct_answer = question.get("correct_answer", "")
        if qtype == "multiple_choice":
            correct_idx = question.get("correct_index", 0)
            is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
            is_partial = False
        else:
            is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
            is_partial = (not is_correct and
                          correct_answer.lower()[:15] in user_answer.lower())

        if is_correct:
            feedback_label.text = "Correcto!"
            feedback_label.style(f"color: {COLORS['green']}; font-weight: bold")
        elif is_partial:
            feedback_label.text = f"~ Parcial. Respuesta: {correct_answer[:80]}"
            feedback_label.style(f"color: {COLORS['yellow']}")
        else:
            feedback_label.text = f"Incorrecto. Respuesta: {correct_answer[:80]}"
            feedback_label.style(f"color: {COLORS['red']}")

        from atenea.scoring import infer_quality
        quality = infer_quality(is_correct, is_partial, q_elapsed_ms)

        results.append({
            "question_id": question["id"],
            "is_correct": is_correct, "is_partial": is_partial,
            "score": 1.0 if is_correct else 0.5 if is_partial else 0.0,
            "quality": quality, "response_time_ms": q_elapsed_ms,
        })

        _update_history(history, question["id"],
                        {"is_correct": is_correct, "is_partial": is_partial, "score": 0}, quality)

    _save_history(project, history)
    summary = _session_summary(results)

    session = {
        "session_id": generate_id("sess"),
        "project": project,
        "date": storage.now_iso(),
        "duration_seconds": round(time.time() - start_time),
        "n_questions": len(results),
        "results": results,
        "summary": summary,
    }
    _save_session(project, session)

    with summary_container:
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("Test Complete").classes("text-xl font-bold mb-4").style(f"color: {COLORS['text']}")
            with ui.row().classes("gap-6"):
                with ui.column().classes("items-center"):
                    acc = summary.get("accuracy", 0)
                    color = COLORS["green"] if acc >= 0.7 else COLORS["yellow"] if acc >= 0.4 else COLORS["red"]
                    ui.label(f"{acc:.0%}").classes("text-4xl font-bold").style(f"color: {color}")
                    ui.label("Accuracy").style(f"color: {COLORS['dim']}")

                with ui.column().classes("items-center"):
                    ui.label(str(summary.get("correct", 0))).classes("text-3xl font-bold").style(f"color: {COLORS['green']}")
                    ui.label("Correct").style(f"color: {COLORS['dim']}")

                with ui.column().classes("items-center"):
                    ui.label(str(summary.get("incorrect", 0))).classes("text-3xl font-bold").style(f"color: {COLORS['red']}")
                    ui.label("Incorrect").style(f"color: {COLORS['dim']}")

    start_btn.enable()


# ============================================================
# PAGE: ANALYTICS DASHBOARD
# ============================================================

@ui.page("/analytics")
def page_analytics():
    create_header()

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        ui.label("Learning Analytics").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")

        projects = storage.list_projects()
        if not projects:
            ui.label("No projects yet").style(f"color: {COLORS['dim']}")
            return

        project_select = ui.select(
            options=projects, label="Project", value=projects[0],
            on_change=lambda e: render_analytics(e.value, analytics_container),
        ).classes("w-48")

        analytics_container = ui.column().classes("w-full")
        render_analytics(projects[0], analytics_container)


def render_analytics(project, container):
    """Render analytics dashboard."""
    container.clear()

    from atenea.analyze import compute_analytics

    analytics = compute_analytics(project)

    with container:
        overall = analytics.get("overall", {})
        level = overall.get("level", "new")
        level_colors = {
            "mastered": COLORS["green"], "familiar": COLORS["yellow"],
            "learning": COLORS["red"], "new": COLORS["dim"],
        }

        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            with ui.row().classes("items-center gap-6"):
                color = level_colors.get(level, COLORS["dim"])
                ui.label(level.upper()).classes("text-3xl font-bold").style(f"color: {color}")
                with ui.column():
                    ui.label(f"Wilson Score: {overall.get('wilson_score', 0):.3f}").style(f"color: {COLORS['text']}")
                    ui.label(f"Reviews: {overall.get('correct', 0)}/{overall.get('total', 0)}").style(f"color: {COLORS['dim']}")

        review = analytics.get("review_status", {})
        with ui.row().classes("gap-4"):
            for label, key, color in [
                ("Tracked", "total_items", COLORS["accent"]),
                ("Due", "due_for_review", COLORS["yellow"]),
                ("Critical", "critical", COLORS["red"]),
                ("New", "new_items", COLORS["dim"]),
            ]:
                with ui.card().classes("p-4 flex-1").style(f"background: {COLORS['card']}"):
                    ui.label(str(review.get(key, 0))).classes("text-2xl font-bold").style(f"color: {color}")
                    ui.label(label).style(f"color: {COLORS['dim']}")

        per_comp = analytics.get("per_component", {})
        if per_comp:
            comp_labels = list(per_comp.keys())
            comp_scores = [per_comp[c]["wilson_score"] for c in comp_labels]

            ui.echart({
                "backgroundColor": COLORS["bg"],
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": comp_labels,
                          "axisLabel": {"color": COLORS["text"], "fontSize": 11}},
                "yAxis": {"type": "value", "max": 1,
                          "axisLabel": {"color": COLORS["dim"]}},
                "series": [{
                    "type": "bar",
                    "data": [
                        {"value": v, "itemStyle": {
                            "color": COLORS["green"] if v >= 0.85 else
                                     COLORS["yellow"] if v >= 0.5 else COLORS["red"]
                        }}
                        for v in comp_scores
                    ],
                    "label": {"show": True, "position": "top",
                              "color": COLORS["text"], "formatter": "{c}"},
                }],
            }).classes("w-full").style("height: 300px")

        trends = analytics.get("session_trends", [])
        if trends:
            ui.label("Session Trends").classes("text-lg font-semibold mt-4").style(f"color: {COLORS['text']}")
            dates = [t.get("date", "?")[:10] for t in trends]
            accs = [round(t.get("accuracy", 0) * 100) for t in trends]

            ui.echart({
                "backgroundColor": COLORS["bg"],
                "tooltip": {"trigger": "axis"},
                "xAxis": {"type": "category", "data": dates,
                          "axisLabel": {"color": COLORS["dim"]}},
                "yAxis": {"type": "value", "max": 100, "name": "Accuracy %",
                          "axisLabel": {"color": COLORS["dim"]}},
                "series": [{
                    "type": "line",
                    "data": accs,
                    "smooth": True,
                    "areaStyle": {"opacity": 0.2},
                    "lineStyle": {"color": COLORS["accent"]},
                    "itemStyle": {"color": COLORS["accent"]},
                }],
            }).classes("w-full").style("height: 250px")


# ============================================================
# PAGE: OPTIMIZATION ANALYSIS
# ============================================================

@ui.page("/optimizer")
def page_optimizer():
    create_header()

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        ui.label("Pipeline Optimization Analysis").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")
        ui.label("Analysis of speed, precision, efficiency, effectiveness, and cost").style(
            f"color: {COLORS['dim']}"
        )

        projects = storage.list_projects()
        project = projects[0] if projects else None

        if not project:
            ui.label("No project data to analyze").style(f"color: {COLORS['dim']}")
            return

        sources = storage.list_sources(project)
        source_id = sources[-1] if sources else None
        clean_md = storage.load_json(
            storage.get_source_path(project, source_id, "clean-md.json")
        ) if source_id else {}
        data = storage.load_json(
            storage.get_source_path(project, source_id, "data.json")
        ) if source_id else {}
        preguntas = storage.load_json(
            storage.get_project_path(project, "preguntas.json")
        ) or {}

        n_sections = len(clean_md.get("sections", []))
        n_paths = len(data.get("paths", []))
        n_points = len(data.get("points", []))
        ext_stats = data.get("extraction_stats", {})

        # ---- SPEED ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("SPEED").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")
            ui.markdown("""
**Bottleneck: LLM API calls in extract.py (Steps 3a-3f)**

| Step | Calls | Est. Time | Bottleneck |
|------|-------|-----------|------------|
| Convert (Marker) | 0 API | 2-4 min | OCR models |
| Chunk | 0 API | <1s | Procedural |
| Extract Points | N sections | 30-90s | Sequential API |
| Extract Paths | N sections | 60-180s | Largest prompts |
| Orphan Recovery | 1 call | 3-8s | Second pass |
| Map Expansion | 1 call | 3-8s | Second pass |
| Generate (lite) | 0 API | <1s | Procedural |
| Generate (MC) | N paths x N comps | 5-30 min | Massive volume |
""")

        # ---- PRECISION ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("PRECISION").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            just_rate = ext_stats.get("justification_verbatim_rate", {}).get("value", 0)
            section_cov = ext_stats.get("section_coverage", {}).get("value", 0)
            keyword_cov = ext_stats.get("keyword_coverage", {}).get("value", 0)
            compliance = ext_stats.get("7pm2_compliance", {}).get("value", 0)
            connectivity = ext_stats.get("point_connectivity", {}).get("value", 0)
            map_cov = ext_stats.get("map_coverage", {}).get("value", 0)

            ui.markdown(f"""
| Metric | Value | Target |
|--------|-------|--------|
| Justification verbatim | **{just_rate:.0%}** | 95% |
| Section coverage | **{section_cov:.0%}** | 100% |
| Keyword coverage | **{keyword_cov:.0%}** | 85% |
| 7+/-2 compliance | **{compliance:.0%}** | 50% |
| Point connectivity | **{connectivity:.0%}** | 60% |
| Map coverage | **{map_cov:.0%}** | 70% |
""")

        # ---- EFFICIENCY ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("EFFICIENCY & COST").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            est_input = n_sections * 3000
            est_output = n_sections * 800
            est_total = est_input + est_output
            est_cost_ds = est_total * 0.00000027

            ui.markdown(f"""
**Token estimate (this document):**

| Phase | Input | Output | Calls | Cost (DeepSeek) |
|-------|-------|--------|-------|-----------------|
| Extract | ~{est_input:,} | ~{est_output:,} | {n_sections * 2 + 4} | ~${est_cost_ds:.4f} |
| Generate (MC) | ~{n_paths * 5 * 2000:,} | — | {n_paths * 5} | ~${n_paths * 5 * 2000 * 0.00000027:.4f} |
| Generate (lite) | 0 | 0 | 0 | $0 |
""")

        # ---- PRIORITY MATRIX ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("OPTIMIZATION PRIORITY MATRIX").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            ui.markdown("""
| # | Optimization | Impact | Effort | Priority |
|---|-------------|--------|--------|----------|
| 1 | Async parallel extraction | High speed | Med | **NEXT** |
| 2 | Extraction cache | High speed | Low | **NEXT** |
| 3 | Prompt compression | Med cost | Med | **NEXT** |
| 4 | Batch API (DeepSeek) | Med cost | Low | **EASY WIN** |
| 5 | Embeddings dedup | High quality | High | **LATER** |
| 6 | CSPOJ validation loop | High quality | Med | **LATER** |
""")


# ============================================================
# ENTRY POINT
# ============================================================

def start_ui(port=8080, reload=False):
    """Launch the developer dashboard."""
    ui.run(
        title="Atenea Developer Dashboard",
        port=port,
        reload=reload,
        dark=True,
        favicon="🦉",
        storage_secret="atenea-dev-dashboard",
    )


if __name__ == "__main__":
    start_ui()

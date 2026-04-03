"""
atenea/ui/app.py — Developer Dashboard (NiceGUI)

A developer-focused UI to visualize pipeline internals, monitor progress,
inspect data structures, and understand optimization opportunities.

Launch: atenea ui [--port 8080]
   or: python -m atenea.ui.app

This is NOT the end-user interface — it's a developer tool for understanding
the pipeline "under the hood" and iterating on optimizations.
"""

import asyncio
import json
import os
import time
import threading
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

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
    pipeline_log = []
    pipeline_running = False
    pipeline_step = ""
    pipeline_progress = 0.0
    pipeline_timings = {}  # step_name -> seconds


state = State()

# Color palette
COLORS = {
    "bg": "#0f1117",
    "card": "#1a1d27",
    "accent": "#6366f1",
    "accent2": "#8b5cf6",
    "green": "#22c55e",
    "yellow": "#eab308",
    "red": "#ef4444",
    "dim": "#6b7280",
    "text": "#e5e7eb",
}


# ============================================================
# LAYOUT
# ============================================================

def create_header():
    """Top navigation bar."""
    with ui.header().classes("items-center justify-between px-6 py-2").style(
        f"background: {COLORS['card']}; border-bottom: 1px solid #2d3348"
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


# ============================================================
# PAGE: PIPELINE (main)
# ============================================================

@ui.page("/")
def page_pipeline():
    create_header()

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        ui.label("Pipeline Runner").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")
        ui.label("Run the full pipeline with live progress visualization").style(f"color: {COLORS['dim']}")

        # Project selector + PDF upload
        with ui.card().classes("w-full p-4").style(f"background: {COLORS['card']}"):
            with ui.row().classes("w-full items-end gap-4"):
                projects = storage.list_projects()
                project_select = ui.select(
                    options=projects or ["(no projects)"],
                    label="Project",
                    value=projects[0] if projects else None,
                ).classes("w-48")

                new_project_input = ui.input("New project name").classes("w-48")

                pdf_upload = ui.upload(
                    label="Drop PDF here",
                    auto_upload=True,
                    on_upload=lambda e: handle_pdf_upload(e, new_project_input, project_select),
                ).classes("w-64").props('accept=".pdf"')

        # Pipeline steps visualization
        with ui.card().classes("w-full p-4").style(f"background: {COLORS['card']}"):
            ui.label("Pipeline Steps").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")

            steps_container = ui.column().classes("w-full gap-2")
            with steps_container:
                step_widgets = {}
                for step_name, step_label, step_icon in [
                    ("convert", "Step 1: PDF → Markdown", "description"),
                    ("chunk", "Step 2: Markdown → clean-md.json", "grid_view"),
                    ("extract", "Step 3: Extract CSPOJ (AI)", "psychology"),
                    ("generate", "Step 4: Generate Questions", "help_outline"),
                ]:
                    with ui.row().classes("w-full items-center gap-3 p-2 rounded").style(
                        "background: #22253a"
                    ) as step_row:
                        icon = ui.icon(step_icon).classes("text-2xl").style(f"color: {COLORS['dim']}")
                        with ui.column().classes("flex-grow"):
                            label = ui.label(step_label).classes("font-medium").style(f"color: {COLORS['text']}")
                            with ui.row().classes("w-full items-center gap-2"):
                                progress = ui.linear_progress(value=0, show_value=False).classes("flex-grow")
                                progress.style("height: 6px")
                                time_label = ui.label("").classes("text-xs").style(f"color: {COLORS['dim']}; min-width: 80px")
                                count_label = ui.label("").classes("text-xs").style(f"color: {COLORS['dim']}; min-width: 120px")
                        status_icon = ui.icon("radio_button_unchecked").classes("text-lg").style(f"color: {COLORS['dim']}")

                    step_widgets[step_name] = {
                        "row": step_row, "icon": icon, "label": label,
                        "progress": progress, "time_label": time_label,
                        "count_label": count_label, "status_icon": status_icon,
                    }

        # Run button
        with ui.row().classes("gap-4"):
            run_btn = ui.button("Run Full Pipeline", icon="play_arrow",
                                on_click=lambda: run_pipeline(
                                    project_select.value or new_project_input.value,
                                    step_widgets, log_area, run_btn,
                                )).props("color=indigo").classes("px-6")

            run_extract_only = ui.button("Extract Only", icon="psychology",
                                         on_click=lambda: run_single_step(
                                             "extract", project_select.value,
                                             step_widgets, log_area,
                                         )).props("outline color=purple").classes("px-4")

            run_generate_only = ui.button("Generate Only", icon="help_outline",
                                           on_click=lambda: run_single_step(
                                               "generate", project_select.value,
                                               step_widgets, log_area,
                                           )).props("outline color=purple").classes("px-4")

        # Live log area
        with ui.card().classes("w-full p-4").style(f"background: {COLORS['card']}"):
            ui.label("Live Log").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
            log_area = ui.log(max_lines=200).classes("w-full h-64").style(
                "font-family: 'JetBrains Mono', monospace; font-size: 12px; "
                f"background: {COLORS['bg']}; color: {COLORS['text']}"
            )

        # Timing summary
        with ui.card().classes("w-full p-4").style(f"background: {COLORS['card']}"):
            ui.label("Performance Timings").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
            timing_chart_container = ui.column().classes("w-full")


async def handle_pdf_upload(e: UploadEventArguments, name_input, project_select):
    """Handle PDF file upload."""
    file = e.file
    content = await file.read()
    project = name_input.value or "uploaded"

    # Save to temp
    tmp_path = Path(f"/tmp/atenea_upload_{file.name}")
    tmp_path.write_bytes(content)

    name_input.value = project
    ui.notify(f"PDF uploaded: {file.name} ({len(content):,} bytes)", type="positive")


async def run_pipeline(project_name, step_widgets, log_area, run_btn):
    """Run the full pipeline with live UI updates."""
    if not project_name or project_name == "(no projects)":
        ui.notify("Select or create a project first", type="warning")
        return

    run_btn.disable()
    log_area.clear()
    state.pipeline_timings = {}

    # Check for uploaded PDF
    uploads = list(Path("/tmp").glob("atenea_upload_*.pdf"))
    pdf_path = str(uploads[0]) if uploads else None

    steps = []
    if pdf_path:
        steps.append(("convert", pdf_path, project_name))
    steps.append(("chunk", project_name, None))
    steps.append(("extract", project_name, None))
    steps.append(("generate", project_name, None))

    for step_name, arg1, arg2 in steps:
        await _run_step(step_name, arg1, arg2, step_widgets, log_area)

    # Show timing chart
    _show_timing_chart(step_widgets)
    run_btn.enable()
    ui.notify("Pipeline complete!", type="positive")


async def run_single_step(step_name, project_name, step_widgets, log_area):
    """Run a single pipeline step."""
    if not project_name:
        ui.notify("Select a project first", type="warning")
        return
    log_area.clear()
    await _run_step(step_name, project_name, None, step_widgets, log_area)
    _show_timing_chart(step_widgets)


async def _run_step(step_name, arg1, arg2, step_widgets, log_area):
    """Execute a single pipeline step with progress tracking."""
    w = step_widgets.get(step_name)
    if not w:
        return

    # Reset UI
    w["status_icon"].name = "hourglass_empty"
    w["status_icon"].style(f"color: {COLORS['yellow']}")
    w["progress"].set_value(0)
    w["time_label"].text = "running..."
    w["count_label"].text = ""
    log_area.push(f"\n{'='*60}")
    log_area.push(f"  STEP: {step_name.upper()}")
    log_area.push(f"{'='*60}")

    start = time.time()

    try:
        result = await run.io_bound(lambda: _execute_step(step_name, arg1, arg2, log_area, w))
        elapsed = time.time() - start
        state.pipeline_timings[step_name] = elapsed

        w["progress"].set_value(1.0)
        w["status_icon"].name = "check_circle"
        w["status_icon"].style(f"color: {COLORS['green']}")
        w["time_label"].text = f"{elapsed:.1f}s"

        log_area.push(f"  ✓ {step_name} completed in {elapsed:.1f}s")

    except Exception as e:
        elapsed = time.time() - start
        state.pipeline_timings[step_name] = elapsed

        w["status_icon"].name = "error"
        w["status_icon"].style(f"color: {COLORS['red']}")
        w["time_label"].text = f"{elapsed:.1f}s (FAILED)"
        log_area.push(f"  ✗ ERROR: {e}")


def _execute_step(step_name, arg1, arg2, log_area, widgets):
    """Execute a pipeline step (runs in thread)."""
    if step_name == "convert":
        from atenea.convert import convert_pdf_to_markdown
        pdf_path, project = arg1, arg2
        log_area.push(f"  Converting: {Path(pdf_path).name}")
        result = convert_pdf_to_markdown(pdf_path, project)
        log_area.push(f"  Output: {result}")
        return result

    elif step_name == "chunk":
        from atenea.chunk import chunk_markdown, split_into_sections, extract_lines, extract_keywords
        project = arg1
        from atenea.chunk import load_markdown
        md_text, source_id = load_markdown(project)
        log_area.push(f"  Loaded: {len(md_text):,} chars from {source_id}")

        # Section splitting with progress
        sections = split_into_sections(md_text)
        log_area.push(f"  Sections: {len(sections)}")
        widgets["count_label"].text = f"{len(sections)} sections"
        widgets["progress"].set_value(0.3)

        # Line extraction
        lines = extract_lines(md_text, sections)
        log_area.push(f"  Lines: {len(lines)}")
        widgets["count_label"].text = f"{len(lines)} lines"
        widgets["progress"].set_value(0.6)

        # Keywords
        keywords = extract_keywords(lines)
        log_area.push(f"  Keywords: {len(keywords)}")
        widgets["count_label"].text = f"{len(sections)}s/{len(lines)}l/{len(keywords)}kw"
        widgets["progress"].set_value(0.9)

        # Build and save
        result = chunk_markdown(project)
        return result

    elif step_name == "extract":
        from atenea.extract import (
            extract_points, extract_paths, extract_sets, extract_maps,
            build_data_json, compute_extraction_stats, run_extraction,
        )
        project = arg1
        sources = storage.list_sources(project)
        source_id = sources[-1] if sources else None
        clean_md_path = storage.get_source_path(project, source_id, "clean-md.json")
        clean_md = storage.load_json(clean_md_path)

        if not clean_md:
            raise FileNotFoundError("No clean-md.json found")

        source_name = clean_md.get("source", "unknown.pdf")
        n_sections = len(clean_md.get("sections", []))

        # Points
        log_area.push(f"  Extracting points from {n_sections} sections...")
        widgets["count_label"].text = "extracting points..."
        t0 = time.time()
        points = extract_points(clean_md)
        t_points = time.time() - t0
        log_area.push(f"  Points: {len(points)} ({t_points:.1f}s)")
        widgets["count_label"].text = f"{len(points)} points"
        widgets["progress"].set_value(0.25)

        # Paths
        log_area.push(f"  Extracting CSPOJ paths...")
        widgets["count_label"].text = "extracting paths..."
        t0 = time.time()
        paths = extract_paths(clean_md, points)
        t_paths = time.time() - t0
        log_area.push(f"  Paths: {len(paths)} ({t_paths:.1f}s)")
        widgets["count_label"].text = f"{len(points)}pt/{len(paths)}paths"
        widgets["progress"].set_value(0.6)

        # Sets
        log_area.push(f"  Extracting sets...")
        widgets["count_label"].text = "extracting sets..."
        t0 = time.time()
        sets = extract_sets(points)
        t_sets = time.time() - t0
        log_area.push(f"  Sets: {len(sets)} ({t_sets:.1f}s)")
        widgets["progress"].set_value(0.8)

        # Maps
        log_area.push(f"  Extracting maps...")
        widgets["count_label"].text = "extracting maps..."
        t0 = time.time()
        maps = extract_maps(paths)
        t_maps = time.time() - t0
        log_area.push(f"  Maps: {len(maps)} ({t_maps:.1f}s)")
        widgets["progress"].set_value(0.9)

        # Build & save
        data = build_data_json(source_name, source_id, points, paths, sets, maps)
        data_path = storage.get_source_path(project, source_id, "data.json")
        storage.save_json(data, data_path)
        project_data_path = storage.get_project_path(project, "data.json")
        storage.save_json(data, project_data_path)

        stats = compute_extraction_stats(data, clean_md)
        data["extraction_stats"] = stats
        storage.save_json(data, data_path)

        # Log timing breakdown
        log_area.push(f"\n  === Extraction Timing ===")
        log_area.push(f"  Points:  {t_points:6.1f}s  ({len(points)} items)")
        log_area.push(f"  Paths:   {t_paths:6.1f}s  ({len(paths)} items)")
        log_area.push(f"  Sets:    {t_sets:6.1f}s  ({len(sets)} items)")
        log_area.push(f"  Maps:    {t_maps:6.1f}s  ({len(maps)} items)")
        total_extract = t_points + t_paths + t_sets + t_maps
        log_area.push(f"  Total:   {total_extract:6.1f}s")

        widgets["count_label"].text = f"{len(points)}pt/{len(paths)}pa/{len(sets)}s/{len(maps)}m"

        return data

    elif step_name == "generate":
        from atenea.generate import generate_questions_lite
        project = arg1
        log_area.push(f"  Generating free-text questions (no LLM)...")
        widgets["count_label"].text = "generating..."
        result = generate_questions_lite(project)
        n = len(result.get("questions", []))
        log_area.push(f"  Questions: {n}")
        widgets["count_label"].text = f"{n} questions"
        widgets["progress"].set_value(1.0)
        return result


def _show_timing_chart(step_widgets):
    """Update timing display after pipeline run."""
    for name, elapsed in state.pipeline_timings.items():
        w = step_widgets.get(name)
        if w:
            w["time_label"].text = f"{elapsed:.1f}s"


# ============================================================
# PAGE: DATA INSPECTOR
# ============================================================

@ui.page("/inspector")
def page_inspector():
    create_header()

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        ui.label("Data Inspector").classes("text-2xl font-bold").style(f"color: {COLORS['text']}")

        # Project selector
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
            # clean-md.json panel
            with ui.tab_panel(tab_md):
                _render_clean_md(project, source_id)

            # data.json panel
            with ui.tab_panel(tab_data):
                _render_data_json(project, source_id)

            # preguntas.json panel
            with ui.tab_panel(tab_preguntas):
                _render_preguntas(project, source_id)

            # Raw JSON panel
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

    # Stats overview
    stats = data.get("stats", {})
    with ui.row().classes("gap-4 mb-4"):
        for label, value in stats.items():
            with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
                ui.label(str(value)).classes("text-2xl font-bold").style(f"color: {COLORS['accent']}")
                ui.label(label.replace("total_", "")).style(f"color: {COLORS['dim']}; font-size: 12px")

    # Sections tree
    ui.label("Section Hierarchy").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
    sections = data.get("sections", [])
    for s in sections:
        indent = "  " * (s["level"] - 1)
        lines_range = f"L{s['start_line']}-{s['end_line']}"
        with ui.row().classes("items-center gap-2"):
            ui.label(f"{indent}{'#' * s['level']}").style(f"color: {COLORS['accent']}; font-family: monospace")
            ui.label(s["title"]).style(f"color: {COLORS['text']}")
            ui.badge(lines_range).props("outline")

    # Keywords word cloud (top 50)
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

    # Stats cards
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
        with ui.row().classes("gap-3 mb-4"):
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

    # CSPOJ Paths table
    ui.label("CSPOJ Paths").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
    paths = data.get("paths", [])

    columns = [
        {"name": "context", "label": "Context", "field": "context", "align": "left"},
        {"name": "subject", "label": "Subject", "field": "subject", "align": "left"},
        {"name": "predicate", "label": "Predicate", "field": "predicate", "align": "left"},
        {"name": "object", "label": "Object", "field": "object", "align": "left"},
        {"name": "pts", "label": "Points", "field": "pts", "align": "center"},
    ]
    rows = [
        {
            "context": p["context"][:40],
            "subject": p["subject"][:30],
            "predicate": p["predicate"][:25],
            "object": p["object"][:30],
            "pts": len(p.get("point_ids", [])),
        }
        for p in paths[:50]  # Limit for performance
    ]
    ui.table(columns=columns, rows=rows, row_key="subject").classes("w-full").style(
        f"background: {COLORS['bg']}"
    )

    # Sets
    ui.label("Semantic Sets").classes("text-lg font-semibold mt-4 mb-2").style(f"color: {COLORS['text']}")
    sets = data.get("sets", [])
    for s in sets:
        with ui.expansion(f"{s['name']} ({len(s.get('point_ids', []))} points)").classes("w-full"):
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

    # Stats
    with ui.row().classes("gap-4 mb-4"):
        ui.card().classes("p-3").style(f"background: {COLORS['card']}")
        with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
            ui.label(str(stats.get("total", 0))).classes("text-2xl font-bold").style(f"color: {COLORS['accent']}")
            ui.label("total questions").style(f"color: {COLORS['dim']}; font-size: 12px")

        by_type = stats.get("by_type", {})
        for qtype, count in by_type.items():
            with ui.card().classes("p-3").style(f"background: {COLORS['card']}"):
                ui.label(str(count)).classes("text-xl font-bold").style(f"color: {COLORS['accent2']}")
                ui.label(qtype).style(f"color: {COLORS['dim']}; font-size: 12px")

    # Distribution by component
    by_comp = stats.get("by_component", {})
    if by_comp:
        ui.label("Questions by Component").classes("text-lg font-semibold mb-2").style(f"color: {COLORS['text']}")
        chart_data = {
            "type": "bar",
            "data": {
                "labels": list(by_comp.keys()),
                "datasets": [{
                    "label": "Questions",
                    "data": list(by_comp.values()),
                    "backgroundColor": ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"],
                }],
            },
            "options": {"plugins": {"legend": {"display": False}}},
        }
        ui.echart(chart_data).classes("w-full h-48") if False else None  # ECharts below

    # Sample questions
    ui.label("Sample Questions").classes("text-lg font-semibold mt-4 mb-2").style(f"color: {COLORS['text']}")
    for q in questions[:15]:
        comp = q.get("component", "?")
        diff = q.get("difficulty", 0)
        diff_color = ["", COLORS["green"], COLORS["green"], COLORS["yellow"],
                      COLORS["yellow"], COLORS["red"]]
        color = diff_color[min(diff, 5)] if diff else COLORS["dim"]

        with ui.card().classes("w-full p-3 mb-1").style(f"background: #22253a"):
            with ui.row().classes("items-center gap-2"):
                ui.badge(comp, color="purple").props("outline")
                ui.badge(f"diff={diff}").style(f"background: {color}")
                ui.label(q.get("question_text", q.get("statement", ""))[:120]).style(
                    f"color: {COLORS['text']}; font-size: 13px"
                )


def _render_raw_json(project, source_id):
    """Render raw JSON files for inspection."""
    files = ["clean-md.json", "data.json", "source-meta.json"]
    for fname in files:
        if source_id:
            fpath = storage.get_source_path(project, source_id, fname)
        else:
            fpath = storage.get_project_path(project, fname)

        data = storage.load_json(fpath)
        if data:
            with ui.expansion(f"{fname} ({os.path.getsize(fpath):,} bytes)").classes("w-full"):
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

    # Color by set membership
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

    for i, p in enumerate(points[:150]):  # Limit nodes for performance
        nodes.append({
            "id": str(i),
            "name": p["term"][:25],
            "symbolSize": min(8 + p.get("frequency", 1) * 2, 30),
            "itemStyle": {"color": point_set_color.get(p["id"], "#6b7280")},
            "category": 0,
        })

    # Edges: connect points that appear in the same path
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

        chart = ui.echart({
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

        # Legend: sets
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

    # Load questions
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
            # Question card
            with ui.card().classes("w-full p-4 mb-2").style(f"background: {COLORS['card']}"):
                with ui.row().classes("items-center gap-2 mb-2"):
                    ui.badge(f"Q{i+1}/{len(selected)}").props("color=indigo")
                    ui.badge(question.get("component", "?"), color="purple").props("outline")
                    ui.badge(f"diff={question.get('difficulty', '?')}").props("outline")

                ui.label(question.get("question_text", question.get("statement", ""))).classes(
                    "text-lg"
                ).style(f"color: {COLORS['text']}")

                # Answer input
                answer_input = ui.input("Tu respuesta...").classes("w-full mt-2")
                with ui.row().classes("gap-2 mt-2"):
                    submit_btn = ui.button("Submit", icon="send").props("color=indigo")
                    skip_btn = ui.button("Skip", icon="skip_next").props("outline color=grey")

                feedback_label = ui.label("").classes("mt-2")

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

        # Wait for answer
        user_answer = await answer_future
        q_elapsed_ms = 5000  # Simplified timing for UI

        if not user_answer:
            feedback_label.text = "Skipped"
            feedback_label.style(f"color: {COLORS['dim']}")
            results.append({
                "question_id": question["id"],
                "is_correct": False, "is_partial": False,
                "score": 0.0, "quality": 0, "response_time_ms": q_elapsed_ms,
            })
            continue

        # Evaluate (use simple matching for UI, no LLM call)
        correct_answer = question.get("correct_answer", "")
        is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
        is_partial = (not is_correct and
                      correct_answer.lower()[:15] in user_answer.lower())

        if is_correct:
            feedback_label.text = "✓ Correcto!"
            feedback_label.style(f"color: {COLORS['green']}; font-weight: bold")
        elif is_partial:
            feedback_label.text = f"~ Parcial. Respuesta: {correct_answer[:80]}"
            feedback_label.style(f"color: {COLORS['yellow']}")
        else:
            feedback_label.text = f"✗ Incorrecto. Respuesta: {correct_answer[:80]}"
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

    # Save and show summary
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

        # Overall mastery
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            with ui.row().classes("items-center gap-6"):
                color = level_colors.get(level, COLORS["dim"])
                ui.label(level.upper()).classes("text-3xl font-bold").style(f"color: {color}")
                with ui.column():
                    ui.label(f"Wilson Score: {overall.get('wilson_score', 0):.3f}").style(f"color: {COLORS['text']}")
                    ui.label(f"Reviews: {overall.get('correct', 0)}/{overall.get('total', 0)}").style(f"color: {COLORS['dim']}")

        # Review status
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

        # Per-component mastery chart
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

        # Session trends
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
        ui.label("Exhaustive analysis of speed, precision, efficiency, effectiveness, and cost").style(
            f"color: {COLORS['dim']}"
        )

        projects = storage.list_projects()
        project = projects[0] if projects else None

        if not project:
            ui.label("No project data to analyze").style(f"color: {COLORS['dim']}")
            return

        # Load all data for analysis
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

        # ---- SPEED ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("SPEED").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")
            ui.markdown("""
**Current bottleneck: LLM API calls in `extract.py` (Steps 3a-3d)**

| Step | Calls | Estimated Time | Bottleneck |
|------|-------|---------------|------------|
| Convert (Marker) | 0 API | 2-4 min | OCR models (CPU/MPS) |
| Chunk | 0 API | <1s | Purely procedural |
| Extract Points | N sections × 1 call | 30-90s | **Sequential API calls** |
| Extract Paths | N sections × 1 call | 60-180s | **Sequential API calls, largest prompts** |
| Extract Sets | 1 call | 2-5s | Single call |
| Extract Maps | 1 call | 3-8s | Single call |
| Generate (lite) | 0 API | <1s | Procedural |
| Generate (full) | N paths × N components × 1 call | 5-30 min | **Massive API volume** |

**Optimizations available:**

1. **`asyncio` parallel extraction** — Extract points/paths from sections concurrently
   instead of sequentially. Expected speedup: **3-5x** for Steps 3a-3b.
   Effort: Medium. Risk: API rate limits.

2. **Section batching** — Group 2-3 short sections into one LLM call.
   Expected speedup: **30-50% fewer API calls**.
   Effort: Low. Risk: Slightly lower quality for boundary sections.

3. **Cache layer** — Hash clean-md.json → skip re-extraction if unchanged.
   Expected speedup: **100% on re-runs** (0 API calls).
   Effort: Low. Risk: None.

4. **Marker GPU acceleration** — Use CUDA/MPS for OCR models.
   Expected speedup: **3-10x** for Step 1.
   Effort: Low (config change). Risk: Hardware dependency.

5. **Streaming responses** — Use litellm streaming to show partial results.
   Expected speedup: Perceived speed improvement (no actual speedup).
   Effort: Medium. Risk: JSON parsing complexity.
""")

        # ---- PRECISION ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("PRECISION").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            ext_stats = data.get("extraction_stats", {})
            just_rate = ext_stats.get("justification_verbatim_rate", {}).get("value", 0)
            section_cov = ext_stats.get("section_coverage", {}).get("value", 0)
            keyword_cov = ext_stats.get("keyword_coverage", {}).get("value", 0)

            ui.markdown(f"""
**Current metrics from your data:**

| Metric | Value | Target | Gap |
|--------|-------|--------|-----|
| Justification verbatim rate | **{just_rate:.0%}** | 95% | {max(0, 0.95 - just_rate):.0%} |
| Section coverage | **{section_cov:.0%}** | 100% | {max(0, 1.0 - section_cov):.0%} |
| Keyword coverage | **{keyword_cov:.0%}** | 85% | {max(0, 0.85 - keyword_cov):.0%} |

**Optimizations available:**

1. **Verbatim enforcement** — Add post-processing to verify justifications exist
   in source text. Auto-retry with stricter prompt if verification fails.
   Expected improvement: **+15-20% verbatim rate**.
   Effort: Medium. Cost: +1 retry call per failed verification.

2. **Fuzzy keyword matching** — Use Levenshtein/ngram matching instead of exact
   match for keyword coverage. The LLM generates compound terms ("fracaso renal agudo")
   while keywords are atomic ("fracaso", "renal", "agudo").
   Expected improvement: **keyword coverage 4% → 60-70%**.
   Effort: Low. Cost: Zero (procedural).

3. **OCR error correction** — Post-process Marker output to fix common OCR errors
   (FÃA → FRA, ÅFG → TFG). Dictionary-based replacement.
   Expected improvement: **Cleaner text → better extraction**.
   Effort: Low. Cost: Zero.

4. **Two-pass extraction** — First pass: extract broadly. Second pass: verify
   and refine with cross-references between sections.
   Expected improvement: **+10-15% point connectivity**.
   Effort: High. Cost: 2x API calls.

5. **Section header normalization** — Chunk.py detects headers inconsistently
   (mix of L1/L4 due to Marker formatting). Normalize with regex.
   Expected improvement: **Better section hierarchy → better scoped extraction**.
   Effort: Low. Cost: Zero.
""")

        # ---- EFFICIENCY (tokens/cost) ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("EFFICIENCY & COST").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            n_sections = len(clean_md.get("sections", []))
            n_paths = len(data.get("paths", []))
            n_points = len(data.get("points", []))

            # Estimate tokens
            est_input = n_sections * 3000  # avg tokens per section prompt
            est_output = n_sections * 800
            est_total = est_input + est_output
            est_cost_ds = est_total * 0.00000027  # DeepSeek pricing approx

            ui.markdown(f"""
**Token consumption estimate (this document):**

| Phase | Input tokens | Output tokens | API calls | Est. cost (DeepSeek) |
|-------|-------------|---------------|-----------|---------------------|
| Points | ~{n_sections * 2000:,} | ~{n_sections * 500:,} | {n_sections} | ~${n_sections * 2500 * 0.00000027:.4f} |
| Paths | ~{n_sections * 3500:,} | ~{n_sections * 1500:,} | {n_sections} | ~${n_sections * 5000 * 0.00000027:.4f} |
| Sets | ~1,000 | ~500 | 1 | ~$0.0004 |
| Maps | ~2,000 | ~1,000 | 1 | ~$0.0008 |
| **Total extract** | **~{est_input:,}** | **~{est_output:,}** | **{n_sections * 2 + 2}** | **~${est_cost_ds:.4f}** |

**Generate (full mode):** ~{n_paths * 5} calls × ~2000 tokens = ~{n_paths * 5 * 2000:,} tokens
→ ~${n_paths * 5 * 2000 * 0.00000027:.4f}

**Optimizations available:**

1. **Prompt compression** — Send keywords + minimal context instead of full section text.
   Expected savings: **30-40% fewer input tokens**.
   Effort: Medium. Risk: Lower context for LLM.

2. **Incremental extraction** — Only extract from new/changed sources.
   Expected savings: **100% for unchanged sources**.
   Effort: Low. Risk: None.

3. **Model tiering** — Use cheap model (DeepSeek) for points, better model
   for paths where quality matters more.
   Expected savings: **Optimized quality/cost ratio**.
   Effort: Already supported via config/models.py!

4. **Batch API calls** — DeepSeek supports batch mode with 50% discount.
   Expected savings: **50% cost reduction** (but higher latency).
   Effort: Low. Risk: Longer wait.

5. **Question generation without LLM** — Free-text mode (current lite mode)
   needs zero API calls. T/F and MC are the expensive modes.
   Current: lite mode generates {len(preguntas.get('questions', []))} questions at $0.
""")

        # ---- EFFECTIVENESS ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("EFFECTIVENESS").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            ui.markdown(f"""
**Current CSPOJ quality (this document):**
- Points: **{n_points}** unique concepts extracted
- Paths: **{n_paths}** CSPOJ pentads
- Paths/section: **{n_paths / max(n_sections, 1):.1f}** (target: 3-15)
- Points with ≥2 connections: **{ext_stats.get('point_connectivity', {}).get('value', 0):.0%}** (target: 60%)

**Optimizations available:**

1. **Point deduplication with embeddings** — Use sentence-transformers to merge
   semantically similar points ("FRA" vs "fracaso renal agudo").
   Expected improvement: **Fewer, higher-quality points → better paths**.
   Effort: High. Cost: Embedding model (~2GB).

2. **Cross-source conflict detection** — When multiple PDFs cover the same topic,
   detect contradictions between CSPOJ paths.
   Expected improvement: **Higher confidence in knowledge base**.
   Effort: High. Cost: Additional LLM calls.

3. **CSPOJ validation loop** — After extraction, run a validation pass where
   the LLM checks each path for logical consistency and completeness.
   Expected improvement: **+10-20% path quality**.
   Effort: Medium. Cost: N additional API calls.

4. **Adaptive question difficulty** — The current system generates questions at
   fixed Bloom levels per component. Track actual difficulty from student
   performance and adjust.
   Expected improvement: **Better learning outcomes (ZPD alignment)**.
   Effort: Medium. Cost: Zero (uses analytics data).

5. **Spaced repetition calibration** — SM-2 default parameters (EF=2.5,
   intervals 1/6/n*EF) may not be optimal. Analyze actual retention data
   to calibrate.
   Expected improvement: **Optimal review scheduling**.
   Effort: Low (after collecting enough data). Cost: Zero.
""")

        # ---- PRIORITY MATRIX ----
        with ui.card().classes("w-full p-6").style(f"background: {COLORS['card']}"):
            ui.label("OPTIMIZATION PRIORITY MATRIX").classes("text-xl font-bold").style(f"color: {COLORS['accent']}")

            ui.markdown("""
| # | Optimization | Impact | Effort | Cost | Priority |
|---|-------------|--------|--------|------|----------|
| 1 | Fuzzy keyword matching | High precision | Low | $0 | **DO NOW** |
| 2 | OCR error correction | Med precision | Low | $0 | **DO NOW** |
| 3 | Section header normalization | Med precision | Low | $0 | **DO NOW** |
| 4 | Extraction cache | High speed | Low | $0 | **DO NOW** |
| 5 | Async parallel extraction | High speed | Med | $0 | **DO NEXT** |
| 6 | Verbatim enforcement | High precision | Med | +$0.01 | **DO NEXT** |
| 7 | Prompt compression | Med cost | Med | -30% | **DO NEXT** |
| 8 | Section batching | Med speed | Low | -30% | **DO NEXT** |
| 9 | Marker GPU | High speed | Low | $0 | **IF AVAILABLE** |
| 10 | Batch API (DeepSeek) | Med cost | Low | -50% | **EASY WIN** |
| 11 | Embeddings dedup | High effectiveness | High | Model | **LATER** |
| 12 | CSPOJ validation loop | High effectiveness | Med | +$0.02 | **LATER** |
| 13 | Two-pass extraction | Med precision | High | 2x | **LATER** |
| 14 | Cross-source conflicts | Med effectiveness | High | +$0.01 | **LATER** |
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

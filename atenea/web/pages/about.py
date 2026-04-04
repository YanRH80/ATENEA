"""
atenea/web/pages/about.py — Methodology and transparency panel
"""

from nicegui import ui

from atenea.web.components.header import render_header
from atenea import __version__, __version_date__


def render():
    """Render the About page."""
    render_header()

    with ui.column().classes("w-full max-w-3xl mx-auto px-6 py-8"):
        ui.label("Acerca de ATENEA").classes("text-2xl font-bold text-slate-100 mb-6")

        _section(
            "Que hace",
            [
                "Extrae entidades y relaciones de textos medicos (keywords, asociaciones, secuencias)",
                "Genera preguntas tipo MIR/ENARM con 5 opciones y justificacion verbatim",
                "Programa revisiones con repeticion espaciada (SM-2)",
                "Visualiza el grafo de conocimiento con cobertura por concepto",
            ],
        )

        _section(
            "Que NO hace",
            [
                "No genera conocimiento nuevo — solo estructura lo que ya esta en el texto",
                "No reemplaza la lectura critica del material original",
                "No garantiza cobertura completa del contenido de un documento",
                "No es un sustituto del criterio clinico",
            ],
        )

        _section(
            "Fundamentos",
            [
                "Repeticion espaciada: SM-2 (Wozniak P., 1990. Optimization of repetition spacing in the practice of learning)",
                "Extraccion: Prompt engineering estructurado sobre LLM, con citas verbatim del texto fuente como ground truth",
                "Evidencia: Clasificacion SIGN/NICE adaptada (niveles 1++ a 4, grado A-D)",
                "Capacidad de memoria: Regla 7±2 (Miller, 1956) para longitud de secuencias",
            ],
        )

        _section(
            "Transparencia",
            [
                "Cada relacion extraida incluye cita textual verificable contra la pagina original",
                "Las justificaciones de preguntas incluyen referencia [citekey, p.X]",
                "El status de cada concepto (known/testing/unknown) se basa en datos objetivos: ratio de aciertos y numero de revisiones",
                "Todo el codigo fuente es auditable",
            ],
        )

        # Technical details
        with ui.card().classes("bg-slate-800 w-full p-4 mt-4 border border-slate-700"):
            ui.label("Detalles tecnicos").classes("text-sm font-semibold text-slate-300 mb-2")

            details = [
                f"Version: {__version__} ({__version_date__})",
                "Modelo LLM: Configurable via litellm (DeepSeek, OpenAI, Anthropic, local)",
                "Datos: Almacenados localmente en ~/.atenea/",
                "Sin telemetria. Sin envio de datos a terceros.",
                "Formato: JSON puro, git-friendly, portable",
            ]
            for d in details:
                ui.label(d).classes("text-xs text-slate-400 py-0.5")

        # Back
        ui.button(
            "← Volver",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat color=primary").classes("mt-6")


def _section(title, items):
    """Render a section with bullet points."""
    with ui.card().classes("bg-slate-800 w-full p-4 mb-4 border border-slate-700"):
        ui.label(title).classes("text-lg font-semibold text-slate-200 mb-2")
        for item in items:
            with ui.row().classes("gap-2 items-start"):
                ui.label("•").classes("text-blue-400 mt-0.5")
                ui.label(item).classes("text-sm text-slate-300 leading-relaxed")

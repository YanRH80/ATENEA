"""
atenea/web/pages/test.py — Interactive test session

State machine: SETUP -> QUESTION -> RESULT -> QUESTION -> ... -> SUMMARY
"""

from nicegui import ui

from atenea.web import theme
from atenea.web.components.header import render_header
from atenea.services.test_service import (
    prepare_test,
    evaluate_answer,
    update_coverage,
    finish_test,
)


class TestState:
    """Manages test session state."""

    def __init__(self, project_name, n=25):
        self.project = project_name
        self.n = n
        self.questions = []
        self.coverage = {}
        self.current_idx = 0
        self.results = []
        self.selected_answer = None
        self.phase = "setup"  # setup | question | result | summary
        self.session = None
        self.error = None

    def load(self):
        try:
            data = prepare_test(self.project, n=self.n)
            self.questions = data["questions"]
            self.coverage = data["coverage"]
            self.phase = "question"
        except ValueError as e:
            self.error = str(e)
            self.phase = "setup"

    @property
    def current_question(self):
        if 0 <= self.current_idx < len(self.questions):
            return self.questions[self.current_idx]
        return None

    @property
    def total(self):
        return len(self.questions)

    @property
    def progress(self):
        return self.current_idx / self.total if self.total > 0 else 0

    def submit_answer(self):
        q = self.current_question
        if not q or not self.selected_answer:
            return None

        result = evaluate_answer(q, self.selected_answer)

        # Record
        self.results.append({
            "question_id": q.get("id", ""),
            "answer": self.selected_answer,
            "correct": result["is_correct"],
            "targets": q.get("targets", []),
        })

        # Update coverage
        update_coverage(self.coverage, q.get("targets", []), result["is_correct"])

        self.phase = "result"
        return result

    def next_question(self):
        self.current_idx += 1
        self.selected_answer = None
        if self.current_idx >= self.total:
            self._finish()
        else:
            self.phase = "question"

    def _finish(self):
        self.session = finish_test(self.project, self.results, self.coverage)
        self.phase = "summary"

    def abandon(self):
        if self.results:
            self._finish()
        else:
            self.phase = "summary"
            self.session = {"total": 0, "correct": 0, "score": 0}


def render(project_name: str):
    """Render the test page."""
    render_header(current_project=project_name)

    state = TestState(project_name)
    state.load()

    # Container that gets rebuilt on state changes
    container = ui.column().classes("w-full max-w-3xl mx-auto px-6 py-8")

    def rebuild():
        container.clear()
        with container:
            if state.error:
                _render_error(state)
            elif state.phase == "question":
                _render_question(state, rebuild)
            elif state.phase == "result":
                _render_result(state, rebuild)
            elif state.phase == "summary":
                _render_summary(state)

    rebuild()


def _render_error(state):
    """Show error (no questions available)."""
    with ui.card().classes("bg-slate-800 w-full p-8 border border-red-800"):
        ui.label("No se puede iniciar test").classes("text-xl font-bold text-red-400")
        ui.label(state.error).classes("text-slate-400 mt-2")
        ui.button(
            "Volver al proyecto",
            on_click=lambda: ui.navigate.to(f"/project/{state.project}"),
        ).props("flat color=primary").classes("mt-4")


def _render_question(state, rebuild):
    """Render current question with options."""
    q = state.current_question
    idx = state.current_idx + 1
    total = state.total

    # Progress bar
    ui.linear_progress(value=state.progress, show_value=False).classes("mb-4").props(
        "color=primary rounded"
    )

    with ui.row().classes("w-full items-center justify-between mb-4"):
        ui.label(f"Pregunta {idx}/{total}").classes("text-lg font-bold text-slate-200")
        pattern = q.get("pattern", "general").replace("_", " ")
        ui.label(pattern).classes("text-xs text-slate-500 bg-slate-700 rounded px-2 py-1")

    # Context
    context = q.get("context", "")
    if context:
        with ui.card().classes("bg-slate-700/50 w-full p-4 mb-4 border border-slate-600"):
            ui.label("Contexto clinico").classes("text-xs font-semibold text-cyan-400 mb-1")
            ui.label(context).classes("text-sm text-slate-300 leading-relaxed")

    # Question
    ui.label(q["question"]).classes("text-lg font-semibold text-slate-100 mb-4")

    # Options (A-E)
    options = q.get("options", {})
    radio_group = ui.radio(
        options={k: f"{k})  {v}" for k, v in sorted(options.items())},
        value=None,
    ).classes("w-full").props("color=primary")

    def on_select(e):
        state.selected_answer = e.value

    radio_group.on("update:model-value", on_select)

    # Actions
    with ui.row().classes("w-full justify-between mt-6"):
        ui.button("Abandonar", on_click=lambda: _abandon(state, rebuild)).props(
            "flat color=grey"
        )

        confirm_btn = ui.button(
            "Confirmar",
            on_click=lambda: _submit(state, rebuild),
        ).props("color=primary")

    # Traceability (subtle)
    with ui.row().classes("w-full mt-6 gap-4"):
        targets = q.get("targets", [])
        if targets:
            ui.label(f"Conceptos: {', '.join(targets[:3])}").classes("text-xs text-slate-600")
        diff = q.get("difficulty", "")
        if diff:
            ui.label(f"Dificultad: {diff}/3").classes("text-xs text-slate-600")


def _submit(state, rebuild):
    if not state.selected_answer:
        ui.notify("Selecciona una respuesta", type="warning")
        return
    state.submit_answer()
    rebuild()


def _abandon(state, rebuild):
    state.abandon()
    rebuild()


def _render_result(state, rebuild):
    """Show answer result with justification."""
    q = state.current_question
    idx = state.current_idx + 1
    total = state.total
    last_result = state.results[-1]
    is_correct = last_result["correct"]
    user_answer = last_result["answer"]

    # Progress
    ui.linear_progress(value=state.progress, show_value=False).classes("mb-4").props(
        "color=primary rounded"
    )

    ui.label(f"Pregunta {idx}/{total}").classes("text-lg font-bold text-slate-200 mb-4")

    # Result indicator
    if is_correct:
        with ui.card().classes("bg-green-900/30 w-full p-4 border border-green-700 mb-4"):
            ui.label("Correcto").classes("text-xl font-bold text-green-400")
    else:
        correct = q.get("correct", "")
        correct_text = q.get("options", {}).get(correct, "")
        with ui.card().classes("bg-red-900/30 w-full p-4 border border-red-700 mb-4"):
            ui.label("Incorrecto").classes("text-xl font-bold text-red-400")
            ui.label(
                f"Tu respuesta: {user_answer})  |  Correcta: {correct}) {correct_text}"
            ).classes("text-sm text-slate-300 mt-1")

    # Justification
    justification = q.get("justification", "")
    if justification:
        with ui.card().classes("bg-slate-700/50 w-full p-4 border border-slate-600 mb-4"):
            ui.label("Justificacion").classes("text-xs font-semibold text-green-400 mb-2")
            ui.label(justification).classes("text-sm text-slate-300 leading-relaxed")

    # Next button
    with ui.row().classes("w-full justify-end mt-4"):
        if state.current_idx + 1 < state.total:
            ui.button(
                "Siguiente →",
                on_click=lambda: _next(state, rebuild),
            ).props("color=primary")
        else:
            ui.button(
                "Ver resumen",
                on_click=lambda: _next(state, rebuild),
            ).props("color=primary")


def _next(state, rebuild):
    state.next_question()
    rebuild()


def _render_summary(state):
    """Show test summary with score and breakdown."""
    session = state.session or {"total": 0, "correct": 0, "score": 0}
    total = session.get("total", 0)
    correct = session.get("correct", 0)
    score = session.get("score", 0)

    if total == 0:
        ui.label("Test abandonado sin respuestas.").classes("text-slate-400 text-lg")
        ui.button(
            "Volver al proyecto",
            on_click=lambda: ui.navigate.to(f"/project/{state.project}"),
        ).props("flat color=primary").classes("mt-4")
        return

    # Score header
    color = theme.KNOWN if score >= 70 else theme.TESTING if score >= 50 else theme.UNKNOWN
    with ui.card().classes("bg-slate-800 w-full p-6 border border-slate-700 mb-6"):
        with ui.row().classes("items-center justify-between"):
            with ui.column():
                ui.label("Resultado").classes("text-sm text-slate-400")
                ui.label(f"{correct}/{total}").classes("text-4xl font-bold text-slate-100")
            ui.label(f"{score}%").classes("text-5xl font-bold").style(f"color: {color}")

        # Progress bar
        ui.linear_progress(value=score / 100).classes("mt-4").props(
            f"rounded size=lg"
        ).style(f"color: {color}")

    # Per-question breakdown
    with ui.card().classes("bg-slate-800 w-full p-4 border border-slate-700 mb-6"):
        ui.label("Detalle").classes("text-lg font-semibold text-slate-200 mb-3")

        for i, r in enumerate(state.results):
            q = state.questions[i]
            icon = "check_circle" if r["correct"] else "cancel"
            icon_color = "green" if r["correct"] else "red"
            question_text = q.get("question", "")[:80]

            with ui.row().classes("w-full items-center gap-2 py-1 border-b border-slate-700/50"):
                ui.icon(icon).classes(f"text-{icon_color}-400")
                ui.label(f"{i+1}. {question_text}...").classes("text-sm text-slate-300 flex-1")
                ui.label(r["answer"]).classes("text-xs text-slate-500 font-mono")

    # Actions
    with ui.row().classes("gap-4"):
        ui.button(
            "Nuevo test",
            on_click=lambda: ui.navigate.to(f"/project/{state.project}/test"),
        ).props("color=primary")
        ui.button(
            "Volver al proyecto",
            on_click=lambda: ui.navigate.to(f"/project/{state.project}"),
        ).props("flat color=primary")

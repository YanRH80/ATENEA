"""
atenea/web/pages/test.py — Focused test session

Design: Anki reviewer. Zero distractions. One question, full width, clear feedback.
State machine: QUESTION → RESULT → QUESTION → ... → SUMMARY

No header, no sidebar, no navigation except "Salir".
"""

from nicegui import ui

from atenea.web import theme
from atenea.services.test_service import (
    prepare_test,
    evaluate_answer,
    update_coverage,
    finish_test,
)


class TestState:
    """Test session state."""

    def __init__(self, project_name, n=25):
        self.project = project_name
        self.n = n
        self.questions = []
        self.coverage = {}
        self.current_idx = 0
        self.results = []
        self.selected_answer = None
        self.phase = "setup"
        self.session = None
        self.error = None
        self.last_result = None

    def load(self):
        try:
            data = prepare_test(self.project, n=self.n)
            self.questions = data["questions"]
            self.coverage = data["coverage"]
            self.phase = "question"
        except ValueError as e:
            self.error = str(e)

    @property
    def q(self):
        if 0 <= self.current_idx < len(self.questions):
            return self.questions[self.current_idx]
        return None

    @property
    def total(self):
        return len(self.questions)

    @property
    def progress(self):
        return self.current_idx / self.total if self.total > 0 else 0

    @property
    def correct_so_far(self):
        return sum(1 for r in self.results if r["correct"])

    def submit(self):
        q = self.q
        if not q or not self.selected_answer:
            return
        result = evaluate_answer(q, self.selected_answer)
        self.last_result = result
        self.results.append({
            "question_id": q.get("id", ""),
            "answer": self.selected_answer,
            "correct": result["is_correct"],
            "targets": q.get("targets", []),
        })
        update_coverage(self.coverage, q.get("targets", []), result["is_correct"])
        self.phase = "result"

    def advance(self):
        self.current_idx += 1
        self.selected_answer = None
        self.last_result = None
        if self.current_idx >= self.total:
            self.session = finish_test(self.project, self.results, self.coverage)
            self.phase = "summary"
        else:
            self.phase = "question"

    def abandon(self):
        if self.results:
            self.session = finish_test(self.project, self.results, self.coverage)
        else:
            self.session = {"total": 0, "correct": 0, "score": 0}
        self.phase = "summary"


def render(project_name: str):
    """Render the test page — minimal chrome."""
    state = TestState(project_name)
    state.load()

    # Thin top bar (not the full header)
    with ui.row().classes(
        "w-full items-center px-4 py-2 border-b border-slate-800 bg-slate-900/50"
    ):
        ui.button(
            icon="close",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat dense round color=grey-6")
        ui.label(project_name.upper()).classes("text-sm text-slate-500 ml-2")
        ui.space()
        # Live score
        score_label = ui.label("").classes("text-sm font-mono text-slate-500")

    container = ui.column().classes("w-full max-w-2xl mx-auto px-4 py-6")

    def rebuild():
        container.clear()
        # Update live score
        if state.total > 0 and state.results:
            score_label.text = f"{state.correct_so_far}/{len(state.results)} · {state.current_idx + (0 if state.phase == 'question' else 1)}/{state.total}"
        with container:
            if state.error:
                _error(state)
            elif state.phase == "question":
                _question(state, rebuild)
            elif state.phase == "result":
                _result(state, rebuild)
            elif state.phase == "summary":
                _summary(state)

    rebuild()


# ============================================================
# QUESTION
# ============================================================

def _question(state, rebuild):
    """Single question — maximum clarity."""
    q = state.q
    idx = state.current_idx + 1

    # Progress: thin bar + counter
    with ui.row().classes("w-full items-center gap-3 mb-6"):
        ui.linear_progress(value=state.progress, show_value=False).classes("flex-1").props(
            "color=primary rounded size=xs"
        )
        ui.label(f"{idx}/{state.total}").classes("text-xs text-slate-500 font-mono min-w-[40px] text-right")

    # Context (if clinical scenario)
    context = q.get("context", "")
    if context:
        ui.label(context).classes(
            "text-sm text-slate-400 leading-relaxed mb-4 pl-3 "
            "border-l-2 border-slate-600"
        )

    # Question
    ui.label(q["question"]).classes("text-lg text-slate-100 leading-relaxed mb-6")

    # Options
    options = q.get("options", {})
    radio = ui.radio(
        options={k: f"{k})  {v}" for k, v in sorted(options.items())},
        value=None,
    ).classes("w-full").props("color=primary")

    radio.on("update:model-value", lambda e: setattr(state, 'selected_answer', e.value))

    # Confirm
    with ui.row().classes("w-full justify-between mt-8"):
        ui.button("Salir", on_click=lambda: _do_abandon(state, rebuild)).props(
            "flat dense color=grey-6"
        ).classes("text-xs")

        ui.button(
            "Confirmar",
            on_click=lambda: _do_submit(state, rebuild),
        ).props("unelevated color=primary")

    # Traceability (very subtle, for dev)
    targets = q.get("targets", [])
    pattern = q.get("pattern", "")
    diff = q.get("difficulty", "")
    meta_parts = []
    if targets:
        meta_parts.append(", ".join(targets[:3]))
    if pattern:
        meta_parts.append(pattern.replace("_", " "))
    if diff:
        meta_parts.append(f"d:{diff}/3")
    if meta_parts:
        ui.label(" · ".join(meta_parts)).classes("text-xs text-slate-700 mt-6")


def _do_submit(state, rebuild):
    if not state.selected_answer:
        ui.notify("Selecciona una respuesta", type="warning")
        return
    state.submit()
    rebuild()


def _do_abandon(state, rebuild):
    state.abandon()
    rebuild()


# ============================================================
# RESULT
# ============================================================

def _result(state, rebuild):
    """Answer feedback — green/red + justification."""
    q = state.q
    r = state.last_result
    is_correct = r["is_correct"]

    # Result indicator (compact)
    if is_correct:
        ui.label("✓ Correcto").classes("text-xl font-bold text-green-400 mb-4")
    else:
        correct_letter = r["correct_answer"]
        correct_text = r["correct_text"]
        ui.label("✗ Incorrecto").classes("text-xl font-bold text-red-400 mb-2")
        ui.label(
            f"Tu respuesta: {state.results[-1]['answer']}  →  Correcta: {correct_letter}) {correct_text}"
        ).classes("text-sm text-slate-400 mb-4")

    # Justification
    justification = r.get("justification", q.get("justification", ""))
    if justification:
        with ui.column().classes(
            "w-full p-4 rounded border-l-2 mb-6 "
            + ("border-green-600 bg-green-900/10" if is_correct else "border-red-600 bg-red-900/10")
        ):
            ui.label("Justificación").classes("text-xs font-semibold text-slate-500 mb-2")
            ui.label(justification).classes("text-sm text-slate-300 leading-relaxed")

    # Next
    with ui.row().classes("w-full justify-end"):
        is_last = state.current_idx + 1 >= state.total
        ui.button(
            "Ver resumen" if is_last else "Siguiente →",
            on_click=lambda: _do_advance(state, rebuild),
        ).props("unelevated color=primary")


def _do_advance(state, rebuild):
    state.advance()
    rebuild()


# ============================================================
# SUMMARY
# ============================================================

def _summary(state):
    """End-of-session summary."""
    s = state.session or {"total": 0, "correct": 0, "score": 0}
    total = s.get("total", 0)
    correct = s.get("correct", 0)
    score = s.get("score", 0)

    if total == 0:
        ui.label("Test abandonado sin respuestas.").classes("text-slate-400 text-lg")
        ui.button("Volver", on_click=lambda: ui.navigate.to("/")).props("flat color=primary").classes("mt-4")
        return

    # Score
    color = theme.KNOWN if score >= 70 else theme.TESTING if score >= 50 else theme.UNKNOWN

    with ui.column().classes("items-center w-full py-8"):
        ui.label(f"{score}%").classes("text-6xl font-bold").style(f"color: {color}")
        ui.label(f"{correct}/{total} correctas").classes("text-xl text-slate-300 mt-2")

        # Mastery bar for this session
        correct_pct = correct / total * 100 if total > 0 else 0
        theme.html(f'''
            <div class="mastery-bar" style="width:300px; height:10px; margin-top:16px;">
                <div class="known" style="width:{correct_pct}%"></div>
                <div class="unknown" style="width:{100 - correct_pct}%"></div>
            </div>
        ''')

    # Per-question breakdown (compact table)
    with ui.column().classes("w-full mt-8 gap-0"):
        ui.label("Detalle").classes("text-sm font-semibold text-slate-400 mb-3")

        for i, r in enumerate(state.results):
            q = state.questions[i]
            icon = "●" if r["correct"] else "○"
            icon_color = "text-green-400" if r["correct"] else "text-red-400"
            q_text = q.get("question", "")[:90]
            targets = ", ".join(r.get("targets", [])[:2])

            with ui.row().classes("w-full items-start gap-2 py-1.5 border-b border-slate-800/50"):
                ui.label(icon).classes(f"{icon_color} text-xs mt-1")
                with ui.column().classes("flex-1 gap-0"):
                    ui.label(f"{i+1}. {q_text}").classes("text-sm text-slate-300")
                    if targets:
                        ui.label(targets).classes("text-xs text-slate-600")
                ui.label(r["answer"]).classes("text-xs text-slate-500 font-mono")

    # Actions
    with ui.row().classes("w-full justify-center gap-4 mt-8"):
        ui.button(
            "Nuevo test",
            on_click=lambda: ui.navigate.to(f"/test/{state.project}"),
        ).props("unelevated color=primary")
        ui.button(
            "Análisis",
            on_click=lambda: ui.navigate.to(f"/analysis/{state.project}"),
        ).props("flat color=grey-5")
        ui.button(
            "Dashboard",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat color=grey-6")


# ============================================================
# ERROR
# ============================================================

def _error(state):
    """No questions available."""
    ui.label("No se puede iniciar test").classes("text-xl font-bold text-red-400")
    ui.label(state.error).classes("text-slate-400 mt-2")
    ui.button(
        "Volver",
        on_click=lambda: ui.navigate.to("/"),
    ).props("flat color=primary").classes("mt-4")

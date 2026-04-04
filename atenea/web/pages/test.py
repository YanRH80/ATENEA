"""
atenea/web/pages/test.py — Interactive test session

Design: Anki reviewer focus + exam-style navigation bar.
State machine: QUESTION → RESULT → QUESTION → ... → SUMMARY

Features:
- Keyboard shortcuts: 1-5 select option, Enter confirm, S skip
- Question navigation bar (jump back to unanswered)
- Live timer + accuracy stats
- Skip unanswered questions
"""

import time as _time

from nicegui import ui

from atenea.web import theme
from atenea.services.test_service import (
    prepare_test,
    evaluate_answer,
    update_coverage,
    finish_test,
)


# ============================================================
# STATE
# ============================================================

class TestState:
    """Test session state with timing and navigation."""

    def __init__(self, project_name, n=25):
        self.project = project_name
        self.n = n
        self.questions = []
        self.coverage = {}
        self.current_idx = 0
        self.selected_answer = None
        self.phase = "setup"
        self.session = None
        self.error = None
        self.last_result = None

        # Per-question tracking (indexed by question number)
        self.answers = {}        # {idx: "A"|"B"|...} — selected answers
        self.results = {}        # {idx: {"correct": bool, "answer": str, ...}}
        self.skipped = set()     # {idx, ...}

        # Timing
        self.start_time = None
        self.question_start = None
        self.question_times = {}  # {idx: seconds}

    def load(self):
        try:
            data = prepare_test(self.project, n=self.n)
            self.questions = data["questions"]
            self.coverage = data["coverage"]
            self.phase = "question"
            self.start_time = _time.time()
            self.question_start = _time.time()
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
    def answered_count(self):
        return len(self.results)

    @property
    def correct_count(self):
        return sum(1 for r in self.results.values() if r["correct"])

    @property
    def accuracy_pct(self):
        if not self.results:
            return 0
        return int(self.correct_count / len(self.results) * 100)

    @property
    def elapsed(self):
        if self.start_time:
            return _time.time() - self.start_time
        return 0

    @property
    def progress(self):
        return len(self.results) / self.total if self.total > 0 else 0

    def _record_time(self):
        """Record time spent on current question."""
        if self.question_start is not None:
            self.question_times[self.current_idx] = _time.time() - self.question_start

    def submit(self):
        """Submit answer for current question."""
        q = self.q
        if not q or not self.selected_answer:
            return
        self._record_time()

        result = evaluate_answer(q, self.selected_answer)
        self.last_result = result
        self.answers[self.current_idx] = self.selected_answer
        self.results[self.current_idx] = {
            "question_id": q.get("id", ""),
            "answer": self.selected_answer,
            "correct": result["is_correct"],
            "targets": q.get("targets", []),
        }
        self.skipped.discard(self.current_idx)
        update_coverage(self.coverage, q.get("targets", []), result["is_correct"])
        self.phase = "result"

    def skip(self):
        """Skip current question."""
        self._record_time()
        self.skipped.add(self.current_idx)
        self._go_next()

    def advance(self):
        """Move past result screen to next question."""
        self.selected_answer = None
        self.last_result = None
        self._go_next()

    def _go_next(self):
        """Find next unanswered question, or finish."""
        # Try next sequential question
        for offset in range(1, self.total + 1):
            next_idx = (self.current_idx + offset) % self.total
            if next_idx not in self.results:
                self.current_idx = next_idx
                self.selected_answer = None
                self.question_start = _time.time()
                self.phase = "question"
                return
        # All answered — finish
        self._finish()

    def jump_to(self, idx):
        """Jump to a specific question."""
        if 0 <= idx < self.total:
            self._record_time()
            self.current_idx = idx
            self.selected_answer = self.answers.get(idx)
            self.question_start = _time.time()
            self.phase = "question"

    def _finish(self):
        """Finish test session."""
        self._record_time()
        results_list = [
            self.results[i] for i in sorted(self.results.keys())
        ]
        self.session = finish_test(self.project, results_list, self.coverage)
        self.phase = "summary"

    def abandon(self):
        """Abandon test early."""
        self._record_time()
        if self.results:
            self._finish()
        else:
            self.session = {"total": 0, "correct": 0, "score": 0}
            self.phase = "summary"

    def question_status(self, idx):
        """Get status of a question: 'current', 'correct', 'incorrect', 'skipped', 'unanswered'."""
        if idx == self.current_idx and self.phase in ("question", "result"):
            return "current"
        if idx in self.results:
            return "correct" if self.results[idx]["correct"] else "incorrect"
        if idx in self.skipped:
            return "skipped"
        return "unanswered"

    def format_time(self, seconds=None):
        """Format seconds as mm:ss."""
        s = seconds if seconds is not None else self.elapsed
        m, sec = divmod(int(s), 60)
        return f"{m}:{sec:02d}"


# ============================================================
# RENDER
# ============================================================

def render(project_name: str):
    """Render the test page."""
    state = TestState(project_name)
    state.load()

    # ── Top bar ──────────────────────────────────────────
    with ui.row().classes(
        "w-full items-center px-4 py-2 border-b border-slate-800 bg-slate-900/50"
    ):
        ui.button(
            icon="close",
            on_click=lambda: ui.navigate.to("/"),
        ).props("flat dense round color=grey-6")
        ui.label(project_name.upper()).classes("text-sm text-slate-500 ml-2")
        ui.space()
        # Live stats
        stats_label = ui.label("").classes("text-sm font-mono text-slate-500")
        timer_label = ui.label("0:00").classes("text-sm font-mono text-slate-600 ml-3")

    # Timer update
    def update_timer():
        if state.phase in ("question", "result") and state.start_time:
            timer_label.text = state.format_time()
            if state.results:
                pct = state.accuracy_pct
                stats_label.text = f"{state.correct_count}/{state.answered_count} ({pct}%)"

    ui.timer(1.0, update_timer)

    # ── Navigation bar (question chips) ──────────────────
    nav_container = ui.row().classes(
        "w-full px-4 py-2 gap-1 flex-wrap border-b border-slate-800/50 bg-slate-900/30"
    )

    # ── Main content ─────────────────────────────────────
    container = ui.column().classes("w-full max-w-2xl mx-auto px-4 py-6")

    def rebuild():
        # Update nav bar
        nav_container.clear()
        with nav_container:
            _render_nav_bar(state, rebuild)

        # Update content
        container.clear()
        with container:
            if state.error:
                _error(state)
            elif state.phase == "question":
                _question(state, rebuild)
            elif state.phase == "result":
                _result(state, rebuild)
            elif state.phase == "summary":
                # Hide nav bar in summary
                nav_container.set_visibility(False)
                _summary(state)

    rebuild()


# ============================================================
# NAVIGATION BAR
# ============================================================

_NAV_COLORS = {
    "current": "bg-blue-600 text-white",
    "correct": "bg-green-600/30 text-green-400",
    "incorrect": "bg-red-600/30 text-red-400",
    "skipped": "bg-yellow-600/20 text-yellow-400",
    "unanswered": "bg-slate-700/50 text-slate-500",
}


def _render_nav_bar(state, rebuild):
    """Clickable numbered chips for each question."""
    for i in range(state.total):
        status = state.question_status(i)
        classes = _NAV_COLORS.get(status, _NAV_COLORS["unanswered"])

        btn = ui.button(
            str(i + 1),
            on_click=lambda _, idx=i: _do_jump(state, idx, rebuild),
        ).props("dense flat padding=xs").classes(
            f"min-w-[28px] h-7 text-xs rounded {classes}"
        )
        # Disable jumping from result phase
        if state.phase == "result":
            btn.props("disable")


def _do_jump(state, idx, rebuild):
    """Jump to question (only if in question phase)."""
    if state.phase == "question":
        state.jump_to(idx)
        rebuild()


# ============================================================
# QUESTION
# ============================================================

def _question(state, rebuild):
    """Single question — keyboard accessible."""
    q = state.q
    idx = state.current_idx + 1
    already_answered = state.current_idx in state.results

    # Progress bar
    with ui.row().classes("w-full items-center gap-3 mb-6"):
        ui.linear_progress(value=state.progress, show_value=False).classes("flex-1").props(
            "color=primary rounded size=xs"
        )
        remaining = state.total - state.answered_count
        ui.label(f"{remaining} restantes").classes("text-xs text-slate-500 font-mono")

    # Context
    context = q.get("context", "")
    if context:
        ui.label(context).classes(
            "text-sm text-slate-400 leading-relaxed mb-4 pl-3 border-l-2 border-slate-600"
        )

    # Question
    ui.label(q["question"]).classes("text-lg text-slate-100 leading-relaxed mb-6")

    # Options
    options = q.get("options", {})
    sorted_keys = sorted(options.keys())
    radio = ui.radio(
        options={k: f"{k})  {v}" for k, v in sorted(options.items())},
        value=state.selected_answer,
    ).classes("w-full").props("color=primary")

    radio.on("update:model-value", lambda e: setattr(state, 'selected_answer', e.value))

    # Keyboard shortcuts
    def handle_key(e):
        key = e.key if hasattr(e, 'key') else str(e.args.get('key', ''))
        if state.phase != "question":
            return
        # 1-5 select option
        if key in ('1', '2', '3', '4', '5'):
            key_idx = int(key) - 1
            if key_idx < len(sorted_keys):
                letter = sorted_keys[key_idx]
                state.selected_answer = letter
                radio.value = letter
        # Enter confirm
        elif key == 'Enter':
            if state.selected_answer:
                _do_submit(state, rebuild)
            else:
                _do_skip(state, rebuild)
        # S skip
        elif key.lower() == 's':
            _do_skip(state, rebuild)

    ui.keyboard(on_key=handle_key, ignore=[])

    # Action buttons
    with ui.row().classes("w-full justify-between mt-8 items-center"):
        ui.button("Salir", on_click=lambda: _do_abandon(state, rebuild)).props(
            "flat dense color=grey-6"
        ).classes("text-xs")

        with ui.row().classes("gap-2"):
            # Hints
            ui.label("1-5 · Enter · S=skip").classes("text-xs text-slate-700 self-center mr-2")

            ui.button("Skip", on_click=lambda: _do_skip(state, rebuild)).props(
                "flat dense color=grey-5"
            ).classes("text-xs")

            if already_answered:
                ui.button(
                    "Re-confirmar",
                    on_click=lambda: _do_submit(state, rebuild),
                ).props("unelevated color=primary")
            else:
                ui.button(
                    "Confirmar",
                    on_click=lambda: _do_submit(state, rebuild),
                ).props("unelevated color=primary")

    # Traceability (dev info, very subtle)
    targets = q.get("targets", [])
    pattern = q.get("pattern", "")
    diff = q.get("difficulty", "")
    meta = []
    if targets:
        meta.append(", ".join(targets[:3]))
    if pattern:
        meta.append(pattern.replace("_", " "))
    if diff:
        meta.append(f"d:{diff}/3")
    if meta:
        ui.label(" · ".join(meta)).classes("text-xs text-slate-700 mt-6")


def _do_submit(state, rebuild):
    if not state.selected_answer:
        ui.notify("Selecciona una respuesta", type="warning")
        return
    state.submit()
    rebuild()


def _do_skip(state, rebuild):
    state.skip()
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

    if is_correct:
        ui.label("✓ Correcto").classes("text-xl font-bold text-green-400 mb-4")
    else:
        ui.label("✗ Incorrecto").classes("text-xl font-bold text-red-400 mb-2")
        ui.label(
            f"Tu respuesta: {state.results[state.current_idx]['answer']}  →  "
            f"Correcta: {r['correct_answer']}) {r['correct_text']}"
        ).classes("text-sm text-slate-400 mb-4")

    # Justification
    justification = r.get("justification", q.get("justification", ""))
    if justification:
        border = "border-green-600 bg-green-900/10" if is_correct else "border-red-600 bg-red-900/10"
        with ui.column().classes(f"w-full p-4 rounded border-l-2 mb-6 {border}"):
            ui.label("Justificación").classes("text-xs font-semibold text-slate-500 mb-2")
            ui.label(justification).classes("text-sm text-slate-300 leading-relaxed")

    # Time for this question
    q_time = state.question_times.get(state.current_idx, 0)
    if q_time > 0:
        ui.label(f"Tiempo: {state.format_time(q_time)}").classes("text-xs text-slate-600 mb-4")

    # Keyboard: Enter to advance
    def handle_result_key(e):
        key = e.key if hasattr(e, 'key') else str(e.args.get('key', ''))
        if key == 'Enter':
            _do_advance(state, rebuild)

    ui.keyboard(on_key=handle_result_key, ignore=[])

    # Next button
    unanswered = state.total - state.answered_count
    with ui.row().classes("w-full justify-end items-center gap-2"):
        ui.label("Enter →").classes("text-xs text-slate-700")
        ui.button(
            "Ver resumen" if unanswered == 0 else f"Siguiente ({unanswered} restantes)",
            on_click=lambda: _do_advance(state, rebuild),
        ).props("unelevated color=primary")


def _do_advance(state, rebuild):
    state.advance()
    rebuild()


# ============================================================
# SUMMARY
# ============================================================

def _summary(state):
    """End-of-session summary with timing stats."""
    s = state.session or {"total": 0, "correct": 0, "score": 0}
    total = s.get("total", 0)
    correct = s.get("correct", 0)
    score = s.get("score", 0)

    if total == 0:
        ui.label("Test abandonado sin respuestas.").classes("text-slate-400 text-lg")
        ui.button("Volver", on_click=lambda: ui.navigate.to("/")).props("flat color=primary").classes("mt-4")
        return

    color = theme.KNOWN if score >= 70 else theme.TESTING if score >= 50 else theme.UNKNOWN

    # Score header
    with ui.column().classes("items-center w-full py-8"):
        ui.label(f"{score}%").classes("text-6xl font-bold").style(f"color: {color}")
        ui.label(f"{correct}/{total} correctas").classes("text-xl text-slate-300 mt-2")

        correct_pct = correct / total * 100
        theme.html(f'''
            <div class="mastery-bar" style="width:300px; height:10px; margin-top:16px;">
                <div class="known" style="width:{correct_pct}%"></div>
                <div class="unknown" style="width:{100 - correct_pct}%"></div>
            </div>
        ''')

    # Time stats
    total_time = state.elapsed
    avg_time = total_time / total if total > 0 else 0
    slowest_idx = max(state.question_times, key=state.question_times.get) if state.question_times else None

    with ui.row().classes("w-full justify-center gap-6 mt-4 mb-6"):
        ui.label(f"Tiempo total: {state.format_time(total_time)}").classes("text-sm text-slate-400")
        ui.label(f"Media: {state.format_time(avg_time)}/pregunta").classes("text-sm text-slate-400")
        skipped = len(state.skipped - set(state.results.keys()))
        if skipped > 0:
            ui.label(f"{skipped} sin responder").classes("text-sm text-yellow-400")

    # Per-question breakdown
    with ui.column().classes("w-full mt-4 gap-0"):
        ui.label("Detalle").classes("text-sm font-semibold text-slate-400 mb-3")

        for i in range(state.total):
            q = state.questions[i]
            q_text = q.get("question", "")[:90]
            q_time = state.question_times.get(i, 0)
            targets = ", ".join(q.get("targets", [])[:2])

            if i in state.results:
                r = state.results[i]
                icon = "●" if r["correct"] else "○"
                icon_color = "text-green-400" if r["correct"] else "text-red-400"
                answer = r["answer"]
            else:
                icon = "—"
                icon_color = "text-yellow-400"
                answer = "skip"

            with ui.row().classes("w-full items-start gap-2 py-1.5 border-b border-slate-800/50"):
                ui.label(icon).classes(f"{icon_color} text-xs mt-1")
                with ui.column().classes("flex-1 gap-0"):
                    ui.label(f"{i+1}. {q_text}").classes("text-sm text-slate-300")
                    if targets:
                        ui.label(targets).classes("text-xs text-slate-600")
                with ui.row().classes("gap-2 items-center"):
                    if q_time > 0:
                        ui.label(state.format_time(q_time)).classes("text-xs text-slate-600 font-mono")
                    ui.label(answer).classes("text-xs text-slate-500 font-mono")

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

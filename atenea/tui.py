"""
atenea/tui.py — Terminal UI Components

Interactive menus, prompts, and visual elements for Atenea CLI.
Uses rich for rendering and sys.stdin raw mode for arrow-key navigation.

Design principles:
- Arrow keys + Enter for selection (no typing numbers)
- Immediate visual feedback on selection change
- Consistent color theme from config/theme.py
- Graceful fallback if terminal doesn't support raw mode
"""

import sys
import tty
import termios

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich import box

from config import theme

console = Console()

# ============================================================
# ASCII LOGO
# ============================================================

LOGO = r"""
   _  _____ ___ _  _ ___   _
  /_\|_   _| __| \| | __| /_\
 / _ \ | | | _|| .` | _| / _ \
/_/ \_\|_| |___|_|\_|___/_/ \_\
"""

TAGLINE = "Adaptive learning from documents"


def show_header():
    """Display the Atenea logo and tagline."""
    logo_text = Text(LOGO.rstrip(), style=f"bold {theme.ACCENT}")
    tagline_text = Text(f"  {TAGLINE}\n", style=theme.MUTED)

    panel = Panel(
        Align.center(logo_text + Text("\n") + tagline_text),
        border_style=theme.PANEL_BORDER,
        padding=(0, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


# ============================================================
# ARROW-KEY MENU SELECTION
# ============================================================

def select_menu(options, title=None, descriptions=None, back_label=None):
    """Interactive menu with arrow-key navigation.

    Args:
        options: List of option labels (strings).
        title: Optional title displayed above the menu.
        descriptions: Optional list of description strings (same length as options).
        back_label: If set, adds a back/quit option at the end with this label.

    Returns:
        int — selected index (0-based), or -1 if back/quit selected, or None if Ctrl+C.
    """
    if back_label:
        options = list(options) + [back_label]
        if descriptions:
            descriptions = list(descriptions) + [""]

    selected = 0
    total = len(options)

    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
    except (ValueError, termios.error):
        return _fallback_select(options, title, descriptions, back_label)

    # Calculate how many lines one full render takes
    render_lines = _count_render_lines(options, selected, title, descriptions)
    first_render = True

    try:
        while True:
            if first_render:
                _render_menu_full(options, selected, title, descriptions, back_label)
                render_lines = _count_render_lines(options, selected, title, descriptions)
                first_render = False
            else:
                # Move up and clear previous render, then redraw
                sys.stdout.write(f"\033[{render_lines}A\033[J")
                sys.stdout.flush()
                _render_menu_full(options, selected, title, descriptions, back_label)
                render_lines = _count_render_lines(options, selected, title, descriptions)

            # Read keypress in raw mode
            tty.setraw(fd)
            try:
                key = sys.stdin.read(1)

                if key == "\x1b":
                    seq = sys.stdin.read(2)
                    if seq == "[A":  # Up
                        selected = (selected - 1) % total
                    elif seq == "[B":  # Down
                        selected = (selected + 1) % total
                    elif seq == "[D":  # Left — back
                        if back_label:
                            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                            sys.stdout.write(f"\033[{render_lines}A\033[J")
                            sys.stdout.flush()
                            return -1
                elif key == "\r" or key == "\n":  # Enter
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    sys.stdout.write(f"\033[{render_lines}A\033[J")
                    sys.stdout.flush()
                    if back_label and selected == total - 1:
                        return -1
                    return selected
                elif key == "q" or key == "Q":
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    sys.stdout.write(f"\033[{render_lines}A\033[J")
                    sys.stdout.flush()
                    return None
                elif key == "\x03":  # Ctrl+C
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    sys.stdout.write(f"\033[{render_lines}A\033[J")
                    sys.stdout.flush()
                    return None
                elif key.isdigit():
                    idx = int(key) - 1
                    if 0 <= idx < total:
                        selected = idx
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    except (KeyboardInterrupt, EOFError):
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write(f"\033[{render_lines}A\033[J")
        sys.stdout.flush()
        return None


def _render_menu_full(options, selected, title, descriptions, back_label):
    """Render menu to terminal. Called once per frame."""
    if title:
        console.print(f"  [{theme.HEADER}]{title}[/]")
        console.print()

    for i, opt in enumerate(options):
        is_back = back_label and i == len(options) - 1
        is_selected = i == selected

        if is_selected:
            marker = f"[bold {theme.ACCENT}]>[/]"
            label_style = f"bold {theme.ACCENT}" if not is_back else f"bold {theme.MUTED}"
        else:
            marker = " "
            label_style = "white" if not is_back else theme.MUTED

        console.print(f"  {marker} [{label_style}]{opt}[/]")

        # Show description only for the selected item
        if is_selected and descriptions and i < len(descriptions) and descriptions[i]:
            console.print(f"      [{theme.MUTED}]{descriptions[i]}[/]")

    console.print(f"\n  [{theme.NAV_HINT}]↑↓ navegar  ↵ seleccionar  q salir[/]")


def _count_render_lines(options, selected, title, descriptions):
    """Count how many terminal lines a render will produce."""
    lines = 0
    if title:
        lines += 2  # title + blank
    lines += len(options)  # one per option
    # Description line for selected item
    if descriptions and selected < len(descriptions) and descriptions[selected]:
        lines += 1
    lines += 2  # blank + hint line
    return lines


def _fallback_select(options, title, descriptions, back_label):
    """Fallback numbered selection for non-interactive terminals."""
    if title:
        console.print(f"\n[{theme.HEADER}]{title}[/]\n")

    for i, opt in enumerate(options):
        is_back = back_label and i == len(options) - 1
        style = theme.MUTED if is_back else "white"
        console.print(f"  [{theme.NAV_OPTION_NUMBER}]{i + 1:>3}[/]  [{style}]{opt}[/]")
        if descriptions and i < len(descriptions) and descriptions[i]:
            console.print(f"       [{theme.MUTED}]{descriptions[i]}[/]")

    console.print()
    while True:
        raw = console.input(f"[{theme.NAV_PROMPT_STYLE}]> [/]").strip()
        if raw.lower() == "q":
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                if back_label and idx == len(options) - 1:
                    return -1
                return idx
        except ValueError:
            pass
        console.print(f"[{theme.ERROR}]Introduce 1-{len(options)} o 'q'[/]")


# ============================================================
# TEXT INPUT
# ============================================================

def text_input(prompt_text, default=None, allow_empty=False):
    """Styled text input prompt.

    Args:
        prompt_text: Label to show.
        default: Default value (shown in brackets).
        allow_empty: If False, re-prompts on empty input.

    Returns:
        str — user input, or None if Ctrl+C.
    """
    suffix = f" [{theme.MUTED}]({default})[/]" if default else ""
    try:
        while True:
            value = console.input(
                f"  [{theme.NAV_PROMPT_STYLE}]{prompt_text}{suffix}: [/]"
            ).strip()
            if not value and default:
                return default
            if value or allow_empty:
                return value
            console.print(f"  [{theme.ERROR}]Campo requerido[/]")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return None


# ============================================================
# CONFIRM PROMPT
# ============================================================

def confirm(prompt_text, default=False):
    """Yes/no confirmation prompt.

    Args:
        prompt_text: Question to ask.
        default: Default value (True=yes, False=no).

    Returns:
        bool — True for yes, False for no.
    """
    hint = "S/n" if default else "s/N"
    try:
        raw = console.input(
            f"  [{theme.NAV_PROMPT_STYLE}]{prompt_text} ({hint}): [/]"
        ).strip().lower()
        if not raw:
            return default
        return raw in ("s", "si", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False


# ============================================================
# STATUS INDICATORS
# ============================================================

def status_bar(project_data):
    """Show a compact project status bar.

    Args:
        project_data: Dict with project stats (sources, known, total, last_sync).
    """
    parts = []
    n_sources = project_data.get("sources", 0)
    known = project_data.get("known", 0)
    total = project_data.get("total", 0)

    parts.append(f"[{theme.INFO}]{n_sources}[/] docs")

    if total > 0:
        pct = int(known / total * 100) if total > 0 else 0
        color = theme.SUCCESS if pct >= 80 else theme.WARNING if pct >= 40 else theme.ERROR
        bar_filled = int(pct / 10)
        bar_empty = 10 - bar_filled
        bar = f"[{color}]{'━' * bar_filled}[/][{theme.MUTED}]{'━' * bar_empty}[/]"
        parts.append(f"{bar} {pct}%")
    else:
        parts.append(f"[{theme.MUTED}]sin datos[/]")

    last_sync = project_data.get("last_sync", "never")
    if last_sync != "never":
        parts.append(f"[{theme.MUTED}]sync: {last_sync[:10]}[/]")

    console.print("  " + "  ".join(parts))


def divider(char="─", style=theme.MUTED):
    """Print a horizontal divider."""
    width = min(console.width, 60)
    console.print(f"[{style}]{char * width}[/]")


# ============================================================
# WELCOME / PROJECT BANNERS
# ============================================================

def show_welcome():
    """Display the Atenea logo with a description of the workflow."""
    logo_text = Text(LOGO.rstrip(), style=f"bold {theme.ACCENT}")
    tagline_text = Text(f"  {TAGLINE}\n", style=theme.MUTED)

    workflow = Text.assemble(
        ("  Workflow: ", theme.MUTED),
        ("sync", f"bold {theme.ACCENT}"),
        (" --> ", theme.MUTED),
        ("study", f"bold {theme.ACCENT}"),
        (" --> ", theme.MUTED),
        ("generate", f"bold {theme.ACCENT}"),
        (" --> ", theme.MUTED),
        ("test", f"bold {theme.ACCENT}"),
        (" --> ", theme.MUTED),
        ("review", f"bold {theme.ACCENT}"),
    )

    content = logo_text + Text("\n") + tagline_text + Text("\n") + workflow + Text("\n")

    panel = Panel(
        Align.center(content),
        border_style=theme.PANEL_BORDER,
        padding=(0, 2),
        box=box.ROUNDED,
    )
    console.print(panel)


def show_project_banner(name):
    """Display a project name banner.

    Args:
        name: Project name (displayed in uppercase).
    """
    banner_text = Text(f"  {name.upper()}  ", style=f"bold {theme.ACCENT}")
    panel = Panel(
        banner_text,
        border_style=theme.PANEL_BORDER,
        box=box.HEAVY,
        expand=False,
    )
    console.print(panel)


def show_project_overview(project_data, n_sources=0, n_knowledge=0, n_questions=0, coverage_pct=None):
    """Display a project overview panel with stats and progress checklist.

    Args:
        project_data: dict from project.json.
        n_sources: number of source documents.
        n_knowledge: number of knowledge items (keywords + associations + sequences).
        n_questions: number of generated questions.
        coverage_pct: percentage of known items (0-100), or None.
    """
    lines = []

    # Progress checklist
    check = lambda done: f"[{theme.SUCCESS}][x][/]" if done else f"[{theme.MUTED}][ ][/]"
    lines.append(f"  {check(n_sources > 0)} Sync ({n_sources} docs)")
    lines.append(f"  {check(n_knowledge > 0)} Study ({n_knowledge} items)")
    lines.append(f"  {check(n_questions > 0)} Generate ({n_questions} preguntas)")
    if coverage_pct is not None:
        lines.append(f"  {check(coverage_pct >= 80)} Test ({coverage_pct}% coverage)")
    else:
        lines.append(f"  {check(False)} Test (sin datos)")

    # Last sync
    last_sync = project_data.get("last_sync", "never")
    if last_sync != "never":
        lines.append(f"\n  [{theme.MUTED}]Ultimo sync: {last_sync[:10]}[/]")

    overview = "\n".join(lines)
    panel = Panel(
        overview,
        title=f"[{theme.HEADER}]Progreso[/]",
        border_style=theme.TABLE_BORDER,
        padding=(1, 2),
        expand=False,
    )
    console.print(panel)

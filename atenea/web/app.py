"""
atenea/web/app.py — NiceGUI application entry point

Runs on localhost:8080. All data stays local.
"""

from dotenv import load_dotenv
load_dotenv()

from nicegui import ui, app

from atenea.web import theme


# ============================================================
# DARK THEME
# ============================================================

def _apply_dark_theme():
    """Apply dark theme to all pages."""
    ui.add_head_html(f"""
    <style>
        body {{
            background-color: {theme.BG} !important;
            color: {theme.TEXT} !important;
        }}
        .nicegui-content {{
            background-color: {theme.BG} !important;
        }}
        .q-card {{
            background-color: {theme.CARD_BG} !important;
        }}
        .q-radio__label {{
            color: {theme.TEXT} !important;
        }}
        .q-linear-progress {{
            background-color: {theme.SURFACE} !important;
        }}
    </style>
    """)


# ============================================================
# ROUTES
# ============================================================

@ui.page("/")
def home_page():
    _apply_dark_theme()
    from atenea.web.pages.home import render
    render()


@ui.page("/project/{name}")
def project_page(name: str):
    _apply_dark_theme()
    from atenea.web.pages.project import render
    render(name)


@ui.page("/project/{name}/test")
def test_page(name: str):
    _apply_dark_theme()
    from atenea.web.pages.test import render
    render(name)


@ui.page("/project/{name}/graph")
def graph_page(name: str):
    _apply_dark_theme()
    from atenea.web.pages.graph import render
    render(name)


@ui.page("/about")
def about_page():
    _apply_dark_theme()
    from atenea.web.pages.about import render
    render()


# ============================================================
# ENTRY POINT
# ============================================================

def start():
    """Start the ATENEA web server."""
    ui.run(
        host="127.0.0.1",
        port=8080,
        title="ATENEA",
        dark=True,
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    start()

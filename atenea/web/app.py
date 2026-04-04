"""
atenea/web/app.py — NiceGUI application entry point

3 views: Dashboard (/) → Test (/test/{name}) → Analysis (/analysis/{name})
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
        .q-tab {{
            color: {theme.TEXT_MUTED} !important;
        }}
        .q-tab--active {{
            color: {theme.PRIMARY} !important;
        }}
        .q-tab-panel {{
            padding: 16px 0 !important;
        }}
        .q-tab__indicator {{
            background: {theme.PRIMARY} !important;
        }}
        /* Mastery bar segments */
        .mastery-bar {{
            display: flex;
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            background: {theme.SURFACE};
        }}
        .mastery-bar .known {{ background: {theme.KNOWN}; }}
        .mastery-bar .testing {{ background: {theme.TESTING}; }}
        .mastery-bar .unknown {{ background: {theme.UNKNOWN}; }}
    </style>
    """)


# ============================================================
# ROUTES — 3 views only
# ============================================================

@ui.page("/")
def dashboard_page():
    _apply_dark_theme()
    from atenea.web.pages.dashboard import render
    render()


@ui.page("/test/{name}")
def test_page(name: str):
    _apply_dark_theme()
    from atenea.web.pages.test import render
    render(name)


@ui.page("/analysis/{name}")
def analysis_page(name: str):
    _apply_dark_theme()
    from atenea.web.pages.analysis import render
    render(name)


# ============================================================
# ENTRY POINT
# ============================================================

def start(host="127.0.0.1", port=8080, show=True):
    """Start the ATENEA web server.

    Args:
        host: Bind address (localhost only for medical data privacy)
        port: Port number
        show: If True, open browser automatically
    """
    ui.run(
        host=host,
        port=port,
        title="ATENEA",
        dark=True,
        reload=False,
        show=show,
        show_welcome_message=show,
    )


def start_background(host="127.0.0.1", port=8080):
    """Start web server in a daemon thread (non-blocking).

    Returns the thread object. Server stops when main process exits.
    """
    import threading

    thread = threading.Thread(
        target=start,
        kwargs={"host": host, "port": port, "show": False},
        daemon=True,
        name="atenea-web",
    )
    thread.start()
    return thread


if __name__ in {"__main__", "__mp_main__"}:
    start()

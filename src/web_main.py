"""Launch the web dashboard and open it in the default browser.

Usage:
    venv/bin/python3 -m src.web_main               # http://127.0.0.1:8765
    venv/bin/python3 -m src.web_main --port 9000
    venv/bin/python3 -m src.web_main --no-browser
"""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from .webapp import app

DEFAULT_PORT = 8765


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Network Traffic Monitor — web dashboard")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    url = f"http://127.0.0.1:{args.port}"

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"Network Traffic Monitor running at {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

#!/bin/bash
# Launches the web dashboard and opens it in the default browser.
cd "$(dirname "$0")" || exit 1
exec venv/bin/python3 -m src.web_main

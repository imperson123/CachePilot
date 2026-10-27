#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${CACHEPILOT_PYTHON:-python3}"
if [ -x .venv/bin/python ] && [ -z "${CACHEPILOT_PYTHON:-}" ]; then
  PY=.venv/bin/python
fi
"$PY" -m cachepilot.replay.generate_demo
"$PY" -m streamlit run dashboard.py

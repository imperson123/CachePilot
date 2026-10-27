@echo off
cd /d "%~dp0\.."
if defined CACHEPILOT_PYTHON (
  set "PY=%CACHEPILOT_PYTHON%"
) else if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" -m cachepilot.replay.generate_demo
if errorlevel 1 exit /b 1
"%PY%" -m streamlit run dashboard.py

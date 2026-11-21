@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if not exist "pyproject.toml" goto missing
if exist ".venv\Scripts\python.exe" goto check
where py >nul 2>nul
if errorlevel 1 goto python
py -3.12 -m venv .venv
if errorlevel 1 goto python
goto install
:python
python -m venv .venv
if errorlevel 1 goto failed
goto install
:check
.venv\Scripts\python.exe -c "import streamlit, fpl_ai, pulp, sklearn, lightgbm; from fpl_ai.teams.search import search_teams; from importlib.metadata import version; assert tuple(map(int,version('scikit-learn').split('.')[:2])) == (1,8); assert tuple(map(int,version('streamlit').split('.')[:2])) >= (1,49)" >nul 2>nul
if not errorlevel 1 goto launch
:install
echo First-time setup or dependency update. Later launches skip this step.
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 goto failed
:launch
echo Opening the local dashboard. Public snapshots and the trained model are included.
echo The app refreshes public metadata as needed; full histories download only on request.
echo Keep this window open. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m streamlit run app\main.py
if errorlevel 1 goto failed
exit /b 0
:missing
echo Extract the entire project ZIP before running this file.
pause
exit /b 1
:failed
echo Startup failed. Install Python 3.12 or newer and check the error above.
pause
exit /b 1

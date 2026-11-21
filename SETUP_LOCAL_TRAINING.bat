@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto python
py -3.12 -m venv .venv
if errorlevel 1 goto python
goto install
:python
python -m venv .venv
if errorlevel 1 goto failed
:install
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 goto failed
echo Python training tools are ready. Start the Rust app and use Local ML - Retrain local models.
echo The existing trained model was not replaced.
pause
exit /b 0
:failed
echo Setup failed. Use Python 3.12 or newer and check the error above.
pause
exit /b 1

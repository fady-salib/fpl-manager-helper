@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
where cargo >nul 2>nul
if errorlevel 1 goto missing
cargo build --manifest-path rust\Cargo.toml --release --locked
if errorlevel 1 goto failed
if not exist bin mkdir bin
copy /y rust\target\release\fpl-manager.exe bin\fpl-manager.exe >nul
if errorlevel 1 goto failed
echo Built bin\fpl-manager.exe. Start with RUN_FPL_MANAGER.bat.
pause
exit /b 0
:missing
echo Install Rust stable from https://rustup.rs and Microsoft C++ Build Tools.
echo The release ZIP already includes an executable; compilation is optional.
pause
exit /b 1
:failed
echo Build failed. Check the error above. Existing data and models were preserved.
pause
exit /b 1

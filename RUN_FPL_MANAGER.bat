@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if not exist "bin\fpl-manager.exe" goto missing
if defined FPL_PROJECT_DIR goto custom_resources
if not exist "data\fpl.sqlite" goto resources
if not exist "models\native-model.json" goto resources
goto ready
:custom_resources
if not exist "%FPL_PROJECT_DIR%\data\fpl.sqlite" goto resources
if not exist "%FPL_PROJECT_DIR%\models\native-model.json" goto resources
:ready
if not defined FPL_PORT set "FPL_PORT=7878"
echo Starting FPL Manager - native Rust edition...
echo No Python, Streamlit or Rust installation is needed for the included executable.
powershell -NoProfile -Command "$url='http://127.0.0.1:'+$env:FPL_PORT; try { $r=Invoke-RestMethod ($url+'/api/health') -TimeoutSec 1; if($r.runtime -eq 'Rust' -and ($r.version -in @('0.3.0','0.5.0-beta.3'))){ Start-Process $url; exit 0 }; if($r.runtime -eq 'Rust'){ Write-Error 'An older FPL Manager is running. Close its console window, then run this updated launcher again.'; exit 1 } } catch {}; $p=Start-Process -FilePath (Join-Path (Get-Location) 'bin\fpl-manager.exe') -WorkingDirectory (Get-Location) -PassThru; for($i=0;$i -lt 50;$i++){ if($p.HasExited){ Write-Error 'FPL Manager stopped. Check its console window and that the port is free.'; exit 1 }; try { $r=Invoke-RestMethod ($url+'/api/health') -TimeoutSec 1; if($r.runtime -eq 'Rust' -and ($r.version -in @('0.3.0','0.5.0-beta.3'))){ Start-Process $url; exit 0 } } catch {}; Start-Sleep -Milliseconds 200 }; Write-Error 'The local server did not become ready. Check the FPL Manager console.'; exit 1"
if errorlevel 1 pause
exit /b
:missing
echo The Windows executable is missing. Extract the complete Rust release ZIP.
echo To compile from source, use BUILD_RUST.bat after installing Rust and C++ build tools.
pause
exit /b 1

:resources
echo This is an app-only update. Merge it into your existing fpl-ai-manager folder first.
echo Keep the existing data and models folders. They are not included in this small update.
pause
exit /b 1

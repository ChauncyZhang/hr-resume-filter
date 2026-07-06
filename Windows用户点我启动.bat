@echo off
setlocal

cd /d "%~dp0app" || (
  echo App folder was not found. Keep the app folder next to this launcher.
  pause
  exit /b 1
)

set "PORT=8765"
if not "%HR_RESUME_PORT%"=="" set "PORT=%HR_RESUME_PORT%"
set "URL=http://127.0.0.1:%PORT%"

echo HR Resume Filter
echo Working directory: %cd%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c = New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1', [int]$env:PORT); exit 0 } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
if not errorlevel 1 (
  echo The tool is already running. Opening %URL%
  start "" "%URL%"
  exit /b 0
)

if exist "HRResumeFilter.exe" (
  echo Starting portable app...
  start "" "HRResumeFilter.exe"
  exit /b 0
)

where py >nul 2>nul
if "%errorlevel%"=="0" (
  set "PY_BOOT=py -3"
) else (
  where python >nul 2>nul
  if not "%errorlevel%"=="0" (
    echo.
    echo Python was not found. Please install Python 3.10 or newer.
    echo Download: https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
  )
  set "PY_BOOT=python"
)

%PY_BOOT% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo.
  echo Python is too old. Please install Python 3.10 or newer.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating local Python environment...
  %PY_BOOT% -m venv .venv
  if errorlevel 1 (
    echo Failed to create Python environment.
    pause
    exit /b 1
  )
)

set "PYTHON_BIN=.venv\Scripts\python.exe"

echo Checking dependencies...
"%PYTHON_BIN%" -c "import importlib.util; missing=[name for name in ('pypdf','docx') if importlib.util.find_spec(name) is None]; raise SystemExit(1 if missing else 0)"
if errorlevel 1 (
  echo Installing dependencies...
  "%PYTHON_BIN%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies. Check the network and try again.
    pause
    exit /b 1
  )
)

echo.
echo Starting web page: %URL%
echo If the browser does not open automatically, visit: %URL%
echo Close this window to stop the tool.
echo.

"%PYTHON_BIN%" web_app.py --host 127.0.0.1 --port "%PORT%"
if errorlevel 1 pause

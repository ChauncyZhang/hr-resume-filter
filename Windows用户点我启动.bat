@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0app" || (
  echo 未找到 app 目录，请确认工具包没有被拆散。
  pause
  exit /b 1
)

set "PORT=8765"
if not "%HR_RESUME_PORT%"=="" set "PORT=%HR_RESUME_PORT%"
set "URL=http://127.0.0.1:%PORT%"

echo HR 简历筛选工具
echo 工作目录：%cd%

where py >nul 2>nul
if "%errorlevel%"=="0" (
  set "PY_BOOT=py -3"
) else (
  where python >nul 2>nul
  if not "%errorlevel%"=="0" (
    echo.
    echo 未找到 Python。请先安装 Python 3.10 或更高版本。
    echo 推荐安装方式：https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
  )
  set "PY_BOOT=python"
)

%PY_BOOT% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo.
  echo Python 版本过低，请安装 Python 3.10 或更高版本。
  echo.
  pause
  exit /b 1
)

%PY_BOOT% -c "import socket; sock=socket.socket(); sock.settimeout(0.5); raise SystemExit(0 if sock.connect_ex(('127.0.0.1', int('%PORT%'))) == 0 else 1)"
if not errorlevel 1 (
  echo 工具已经在运行，正在打开页面：%URL%
  start "" "%URL%"
  exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
  echo 首次运行：正在创建本地 Python 环境...
  %PY_BOOT% -m venv .venv
  if errorlevel 1 (
    echo Python 环境创建失败。
    pause
    exit /b 1
  )
)

set "PYTHON_BIN=.venv\Scripts\python.exe"

echo 检查依赖...
"%PYTHON_BIN%" -c "import importlib.util; missing=[name for name in ('pypdf','docx') if importlib.util.find_spec(name) is None]; raise SystemExit(1 if missing else 0)"
if errorlevel 1 (
  echo 正在安装依赖...
  "%PYTHON_BIN%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)

echo.
echo 正在启动网页：%URL%
echo 如果浏览器没有自动打开，请手动访问：%URL%
echo 关闭这个窗口即可停止工具。
echo.

"%PYTHON_BIN%" web_app.py --host 127.0.0.1 --port "%PORT%"
if errorlevel 1 pause

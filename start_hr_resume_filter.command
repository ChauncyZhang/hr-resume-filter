#!/bin/zsh
set -e

cd "$(dirname "$0")" || exit 1

PORT="${HR_RESUME_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"

echo "HR 简历筛选工具"
echo "工作目录：$(pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "未找到 python3。请先安装 Python 3.10 或更高版本。"
  echo "推荐安装方式：https://www.python.org/downloads/macos/"
  echo ""
  read -r "?按回车退出..."
  exit 1
fi

set +e
python3 - <<PY
import socket
sock = socket.socket()
sock.settimeout(0.5)
raise SystemExit(0 if sock.connect_ex(("127.0.0.1", int("${PORT}"))) == 0 else 1)
PY
ALREADY_RUNNING=$?
set -e

if [ "${ALREADY_RUNNING}" -eq 0 ]; then
  echo "工具已经在运行，正在打开页面：${URL}"
  open "${URL}"
  exit 0
fi

if [ ! -d ".venv" ]; then
  echo "首次运行：正在创建本地 Python 环境..."
  python3 -m venv .venv
fi

PYTHON_BIN=".venv/bin/python"
PIP_BIN=".venv/bin/pip"

echo "检查依赖..."
set +e
"${PYTHON_BIN}" - <<'PY'
missing = []
for module, package in [("pypdf", "pypdf"), ("docx", "python-docx")]:
    try:
        __import__(module)
    except ImportError:
        missing.append(package)
if missing:
    raise SystemExit(1)
PY
DEPS_OK=$?
set -e

if [ "${DEPS_OK}" -ne 0 ]; then
  echo "正在安装依赖..."
  "${PIP_BIN}" install -r requirements.txt
fi

echo ""
echo "正在启动网页：${URL}"
echo "如果浏览器没有自动打开，请手动访问：${URL}"
echo "关闭这个窗口即可停止工具。"
echo ""

"${PYTHON_BIN}" web_app.py --host 127.0.0.1 --port "${PORT}"

#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"

echo "=== Babcock CBT Exam Platform ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.10+."
  exit 1
fi

# Create venv if needed
VENV="$BACKEND/.venv"
if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment…"
  python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

# Install deps if needed
if ! python -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies…"
  pip install -q -r "$BACKEND/requirements.txt"
fi

echo ""
echo "Starting server on http://localhost:8000"
echo "  Admin panel : http://localhost:8000/cbt/admin.html  (open cbt/admin.html in browser)"
echo "  Student page: http://localhost:8000/cbt/student.html"
echo "  Login page  : http://localhost:8000/cbt/login.html"
echo ""
echo "Default admin login: admin / Admin@1234"
echo "(Change this immediately after first login!)"
echo ""
echo "Press Ctrl+C to stop."
echo ""

cd "$BACKEND"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload

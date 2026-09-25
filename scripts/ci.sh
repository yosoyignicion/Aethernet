#!/usr/bin/env bash
# CI local de Aethernet: lint, tipos estrictos, código muerto y tests.
# Uso: ./scripts/ci.sh [PYTHON]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${1:-}"
if [ -z "$PY" ]; then
  if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY="python3"; fi
fi

echo "== intérprete: $PY =="

run() {
  echo
  echo "== $* =="
  "$@"
}

run "$PY" -m ruff check src tests

if "$PY" -c "import mypy" >/dev/null 2>&1; then
  run "$PY" -m mypy --strict src/aethernet
else
  echo "AVISO: mypy no instalado; sáltate con '$PY -m pip install mypy'"
fi

if "$PY" -c "import vulture" >/dev/null 2>&1; then
  echo
  echo "== vulture (core/data) =="
  "$PY" -m vulture src/aethernet/core src/aethernet/data
else
  echo "AVISO: vulture no instalado; sáltate con '$PY -m pip install vulture'"
fi

echo
echo "== pytest =="
"$PY" -m pytest -q -p no:cacheprovider

echo
echo "CI local: OK"

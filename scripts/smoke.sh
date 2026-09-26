#!/usr/bin/env bash
# Smoke E2E: arranca la UI headless, comprueba las 7 rutas y /monitor/status.
# Uso: ./scripts/smoke.sh [PYTHON]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${1:-}"
if [ -z "$PY" ]; then
  if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY="python3"; fi
fi

if ! "$PY" -c "import nicegui" >/dev/null 2>&1; then
  echo "AVISO: NiceGUI no instalado; instala con '$PY -m pip install -e .[ui]'"
  exit 0
fi

PORT="${SMOKE_PORT:-8899}"
TMP="$(mktemp -d)"
export XDG_DATA_HOME="$TMP/data" XDG_CONFIG_HOME="$TMP/config" XDG_CACHE_HOME="$TMP/cache"

"$PY" -m aethernet.ui --web --port "$PORT" --no-browser >"$TMP/ui.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true; rm -rf "$TMP"' EXIT

ready=0
for _ in $(seq 1 40); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then ready=1; break; fi
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  echo "La UI no respondió en 20 s. Últimas líneas del log:"
  tail -20 "$TMP/ui.log" || true
  exit 1
fi

status=0
for path in / /espectro /redes /dispositivos /alertas /informes /ajustes; do
  code="$(curl -s --max-time 8 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$path" || true)"
  echo "$path -> $code"
  [ "$code" = "200" ] || status=1
done

if grep -qE "Traceback|ERROR" "$TMP/ui.log"; then
  echo "Errores en el servidor:"
  grep -E "Traceback|ERROR" "$TMP/ui.log" | head
  status=1
fi

echo "== monitor status =="
"$PY" -m aethernet monitor status | tail -4 || true

if [ "$status" -eq 0 ]; then
  echo "Smoke: OK"
else
  echo "Smoke: FALLÓ"; exit 1
fi

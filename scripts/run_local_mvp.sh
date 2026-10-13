#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv-recovery312/bin/python"
NODE_DIR="$ROOT/data/recovery-runtime/node-v22.23.3-linux-x64/bin"
case "${1:-}" in
  backend)
    test -x "$PYTHON" || { echo 'Thiếu Python runtime phục hồi.' >&2; exit 1; }
    cd "$ROOT"
    exec "$PYTHON" -m uvicorn src.main:app --host 127.0.0.1 --port 8000
    ;;
  worker)
    test -x "$PYTHON" || exit 1
    cd "$ROOT"
    exec "$PYTHON" -m scripts.experiment_worker
    ;;
  frontend)
    test -x "$NODE_DIR/node" || { echo 'Thiếu Node runtime phục hồi.' >&2; exit 1; }
    test -f "$ROOT/frontend/.next/standalone/server.js" || { echo 'Cần build frontend trước.' >&2; exit 1; }
    cd "$ROOT/frontend/.next/standalone"
    export HOSTNAME=127.0.0.1 PORT=3111
    exec "$NODE_DIR/node" server.js
    ;;
  build)
    export PATH="$NODE_DIR:$PATH" NODE_OPTIONS=--max-old-space-size=1536
    cd "$ROOT/frontend"
    npm run build -- --webpack
    mkdir -p .next/standalone/.next
    cp -a .next/static .next/standalone/.next/
    cp -a public .next/standalone/
    ;;
  *) echo 'Dùng: bash scripts/run_local_mvp.sh backend|frontend|worker|build' >&2; exit 2 ;;
esac

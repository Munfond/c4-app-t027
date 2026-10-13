#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv-recovery312/bin/python"
NODE_DIR="$ROOT/data/recovery-runtime/node-v22.23.3-linux-x64/bin"
RELEASE_ROOT="$ROOT/data/runtime/frontend-releases"
RELEASE_POINTER="$ROOT/data/runtime/frontend-current"
publish_frontend_release() {
  IFS= read -r BUILD_ID < .next/BUILD_ID || test -n "$BUILD_ID"
  [[ "$BUILD_ID" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Build ID không hợp lệ.' >&2; exit 1; }
  RELEASE_DIR="$RELEASE_ROOT/$BUILD_ID"
  test ! -e "$RELEASE_DIR" || { echo 'Release đã tồn tại; giữ bản cũ.' >&2; exit 1; }
  mkdir -p "$RELEASE_ROOT"
  mkdir "$RELEASE_DIR"
  cp -a .next/standalone/. "$RELEASE_DIR/"
  printf '%s\n' "$RELEASE_DIR" > "$RELEASE_POINTER.tmp"
  mv "$RELEASE_POINTER.tmp" "$RELEASE_POINTER"
  echo "Frontend release: $RELEASE_DIR"
}
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
    test -f "$RELEASE_POINTER" || { echo 'Cần build frontend trước để tạo release.' >&2; exit 1; }
    IFS= read -r RELEASE_DIR < "$RELEASE_POINTER"
    case "$RELEASE_DIR" in "$RELEASE_ROOT/"*) ;; *) echo 'Release path không hợp lệ.' >&2; exit 1 ;; esac
    test -f "$RELEASE_DIR/server.js" || { echo 'Release frontend thiếu server.js.' >&2; exit 1; }
    cd "$RELEASE_DIR"
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
    publish_frontend_release
    ;;
  package)
    cd "$ROOT/frontend"
    test -f .next/standalone/server.js || exit 1
    publish_frontend_release
    ;;
  *) echo 'Dùng: bash scripts/run_local_mvp.sh backend|frontend|worker|build|package' >&2; exit 2 ;;
esac

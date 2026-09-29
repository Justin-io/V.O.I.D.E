#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=========================================================="
echo "    V.O.I.D.E. — Telemetry Anomaly Detection System"
echo "=========================================================="

# 1. Load local environment configuration if present
if [ -f "$DIR/.env" ]; then
    echo "[*] Sourcing environment configuration from $DIR/.env..."
    set -a
    # shellcheck disable=SC1091
    source "$DIR/.env"
    set +a
elif [ -f "$DIR/.env.example" ]; then
    echo "[i] Note: No .env found. Using defaults. (Copy .env.example to .env to configure)"
fi

export VOIDE_IPC_PORT="${VOIDE_IPC_PORT:-8766}"
export PYTHONPATH="$DIR:$PYTHONPATH"

# 2. Check if running in daemon-only mode
if [ "$1" = "--daemon-only" ] || [ "$1" = "-d" ]; then
    echo "[*] Starting V.O.I.D.E. IPC Daemon in foreground mode on port $VOIDE_IPC_PORT..."
    exec python3 -m agent.runtime.ipc_server "$DIR"
fi

# 3. Start Python IPC server in background if not already running on target port
if ! lsof -i :"$VOIDE_IPC_PORT" >/dev/null 2>&1; then
    echo "[*] Launching V.O.I.D.E. IPC Daemon on ws://127.0.0.1:$VOIDE_IPC_PORT..."
    python3 -m agent.runtime.ipc_server "$DIR" &
    IPC_PID=$!
    trap "kill $IPC_PID 2>/dev/null || true" EXIT
    sleep 1.5
else
    echo "[+] IPC Daemon is already active on port $VOIDE_IPC_PORT."
fi

# 4. Launch Flutter Linux Desktop Application
BINARY="$DIR/apps/voide_desktop/build/linux/x64/release/bundle/voide_desktop"
if [ ! -f "$BINARY" ]; then
    echo "[*] Desktop binary not found at $BINARY. Building Linux release..."
    (cd "$DIR/apps/voide_desktop" && flutter build linux --release)
fi

echo "[*] Launching V.O.I.D.E. Desktop UI on DISPLAY=${DISPLAY:-:0} (IPC port $VOIDE_IPC_PORT)..."
exec "$BINARY"

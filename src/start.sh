#!/usr/bin/env bash

set -euo pipefail

source /bootstrap_workspace.sh
bootstrap_workspace
source /bootstrap_flux.sh
if [ "${FLUX_DEV_PRELOAD:-}" == "true" ]; then
    bootstrap_flux
fi
echo "worker-flux: Bootstrap complete; starting runtime services"

start_local_redis() {
    export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
    local redis_ping_output=""
    local redis_start_output=""

    case "${REDIS_URL}" in
        redis://localhost*|redis://127.0.0.1*)
            if ! command -v redis-cli >/dev/null 2>&1; then
                echo "worker-flux: redis-cli is not installed; cannot verify Redis at ${REDIS_URL}" >&2
                exit 1
            fi

            if redis_ping_output="$(redis-cli -u "${REDIS_URL}" ping 2>&1)" && [ "${redis_ping_output}" = "PONG" ]; then
                echo "worker-flux: Redis already available at ${REDIS_URL}"
                return
            fi

            if ! command -v redis-server >/dev/null 2>&1; then
                echo "worker-flux: redis-server is not installed; cannot start local Redis for ${REDIS_URL}" >&2
                exit 1
            fi

            echo "worker-flux: Starting local Redis at ${REDIS_URL}"

            if ! redis_start_output="$(redis-server --daemonize yes --bind 127.0.0.1 --protected-mode yes --save "" --appendonly no 2>&1)"; then
                echo "worker-flux: Redis failed to start at ${REDIS_URL}" >&2
                if [ -n "${redis_start_output}" ]; then
                    echo "worker-flux: ${redis_start_output}" >&2
                fi
                exit 1
            fi

            for _ in 1 2 3 4 5 6 7 8 9 10; do
                if redis_ping_output="$(redis-cli -u "${REDIS_URL}" ping 2>&1)" && [ "${redis_ping_output}" = "PONG" ]; then
                    echo "worker-flux: Redis ready at ${REDIS_URL}"
                    return
                fi
                sleep 1
            done

            echo "worker-flux: Redis failed readiness check at ${REDIS_URL}" >&2
            if [ -n "${redis_ping_output}" ]; then
                echo "worker-flux: redis-cli ping returned: ${redis_ping_output}" >&2
            fi
            exit 1
            ;;
        *)
            echo "worker-flux: Using external Redis at ${REDIS_URL}"
            ;;
    esac
}

# Start SSH server if PUBLIC_KEY is set (enables remote access and dev-sync.sh)
if [ -n "${PUBLIC_KEY:-}" ]; then
    mkdir -p ~/.ssh
    echo "${PUBLIC_KEY}" > ~/.ssh/authorized_keys
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys

    # Generate host keys if they don't exist (removed during image build for security)
    for key_type in rsa ecdsa ed25519; do
        key_file="/etc/ssh/ssh_host_${key_type}_key"
        if [ ! -f "$key_file" ]; then
            ssh-keygen -t "$key_type" -f "$key_file" -q -N ''
        fi
    done

    service ssh start && echo "worker-flux: SSH server started" || echo "worker-flux: SSH server could not be started" >&2
fi

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p 2>/dev/null | grep -Po "libtcmalloc\.so\.\d+" | head -n 1 || true)"
if [ -n "${TCMALLOC}" ]; then
    export LD_PRELOAD="${TCMALLOC}"
    echo "worker-flux: Using tcmalloc via ${TCMALLOC}"
else
    echo "worker-flux: tcmalloc not found; continuing without LD_PRELOAD"
fi

# ---------------------------------------------------------------------------
# GPU pre-flight check
# Verify that the GPU is accessible before starting Flux handler.
# If PyTorch cannot initialize CUDA the worker will never be able to process jobs,
# so we fail fast with an actionable error message.
# ---------------------------------------------------------------------------
echo "worker-flux: Checking GPU availability..."
if ! GPU_CHECK=$(python3 -c "
import torch
try:
    torch.cuda.init()
    name = torch.cuda.get_device_name(0)
    print(f'OK: {name}')
except Exception as e:
    print(f'FAIL: {e}')
    exit(1)
" 2>&1); then
    echo "worker-flux: GPU is not available. PyTorch CUDA init failed:"
    echo "worker-flux: $GPU_CHECK"
    echo "worker-flux: This usually means the GPU on this machine is not properly initialized."
    echo "worker-flux: Please contact RunPod support and report this machine."
    exit 1
fi
echo "worker-flux: GPU available — $GPU_CHECK"

# PID file used by the handler to detect if services are still running
FRONTEND_PID_FILE="/tmp/flux-frontend.pid"
FRONTEND_PID=""

cleanup_background_processes() {
    for pid in "${FRONTEND_PID:-}"; do
        if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
        fi
    done
}

trap cleanup_background_processes EXIT INT TERM

if [ -z "${RUN_MODE:-}" ]; then
    if [ "${SERVE_API_LOCALLY:-false}" == "true" ]; then
        RUN_MODE="local-api"
    else
        RUN_MODE="worker"
    fi
fi

case "${RUN_MODE}" in
    worker|local-api)
        ;;
    *)
        echo "worker-flux: Unsupported RUN_MODE=${RUN_MODE}. Use worker or local-api." >&2
        exit 1
        ;;
esac

echo "worker-flux: Selected RUN_MODE=${RUN_MODE}"

start_local_redis



start_frontend() {
    if [ "${FLUX_FRONTEND_ENABLED:-true}" != "true" ]; then
        echo "worker-flux: Frontend disabled"
        return
    fi

    echo "worker-flux: Starting Flux frontend on :7777"
    python -m uvicorn frontend_app:app --host 0.0.0.0 --port 7777 &
    FRONTEND_PID="$!"
    echo "${FRONTEND_PID}" > "$FRONTEND_PID_FILE"
}

case "${RUN_MODE}" in
    local-api)
        start_frontend

        echo "worker-flux: Starting RunPod Handler in local API mode"
        python -u /handler.py --rp_serve_api --rp_api_host=0.0.0.0
        ;;
    worker)
        echo "worker-flux: Frontend stays disabled in worker mode"

        echo "worker-flux: Starting RunPod Handler in worker mode"
        python -u /handler.py
        ;;
esac

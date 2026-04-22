#!/usr/bin/env bash

set -euo pipefail

bootstrap_log() {
    echo "worker-flux: $*"
}

describe_directory_size() {
    local target_dir="$1"
    du -sh "${target_dir}" 2>/dev/null | awk '{print $1}' || printf 'unknown-size'
}

run_with_progress_logs() {
    local label="$1"
    local target_dir="$2"
    shift 2

    local heartbeat_seconds="${BOOTSTRAP_PROGRESS_HEARTBEAT_SECONDS:-15}"
    local start_ts
    local heartbeat_pid=""
    start_ts="$(date +%s)"

    (
        while true; do
            sleep "${heartbeat_seconds}"
            bootstrap_log "${label} still in progress for ${target_dir}..."
        done
    ) &
    heartbeat_pid="$!"

    "$@"
    local exit_code=$?

    kill "${heartbeat_pid}" 2>/dev/null || true
    wait "${heartbeat_pid}" 2>/dev/null || true

    if [ "${exit_code}" -ne 0 ]; then
        return "${exit_code}"
    fi

    local end_ts
    local elapsed_seconds
    local final_size
    end_ts="$(date +%s)"
    elapsed_seconds="$((end_ts - start_ts))"
    final_size="$(describe_directory_size "${target_dir}")"
    bootstrap_log "${label} finished in ${elapsed_seconds}s (${final_size})"
}

ensure_workspace_alias() {
    if [ ! -e /workspace ] && [ -d /runpod-volume ]; then
        ln -s /runpod-volume /workspace
    fi
}

detect_persistent_root() {
    if [ -n "${WORKSPACE_ROOT:-}" ]; then
        mkdir -p "${WORKSPACE_ROOT}"
        printf '%s\n' "${WORKSPACE_ROOT}"
        return
    fi

    ensure_workspace_alias

    if [ -d /workspace ]; then
        printf '%s\n' "/workspace"
        return
    fi

    if [ -d /runpod-volume ]; then
        printf '%s\n' "/runpod-volume"
        return
    fi

    printf '%s\n' ""
}

reset_incomplete_seed_directory() {
    local target_dir="$1"
    local label="$2"
    local backup_dir="${target_dir}.resetting.$$"

    bootstrap_log "Found incomplete ${label} seed at ${target_dir}; resetting"

    if mv "${target_dir}" "${backup_dir}"; then
        rm -rf "${backup_dir}" >/dev/null 2>&1 || \
            bootstrap_log "Deferred cleanup needed for ${backup_dir}"
        return
    fi

    bootstrap_log "Could not move incomplete ${label} seed; deleting in place"
    rm -rf "${target_dir}"
}

acquire_bootstrap_lock() {
    local lock_dir="$1"
    local timeout_seconds="${BOOTSTRAP_LOCK_TIMEOUT_SECONDS:-600}"
    local poll_seconds="${BOOTSTRAP_LOCK_POLL_SECONDS:-2}"
    local stale_seconds="${BOOTSTRAP_LOCK_STALE_SECONDS:-120}"
    local heartbeat_seconds="${BOOTSTRAP_LOCK_HEARTBEAT_SECONDS:-5}"
    local start_ts
    local now_ts
    local lock_ts

    start_ts="$(date +%s)"

    while ! mkdir "${lock_dir}" 2>/dev/null; do
        now_ts="$(date +%s)"
        lock_ts=0

        if [ -f "${lock_dir}/timestamp" ]; then
            lock_ts="$(cat "${lock_dir}/timestamp" 2>/dev/null || printf '0')"
        fi

        if [ "${lock_ts}" -gt 0 ] && [ $((now_ts - lock_ts)) -ge "${stale_seconds}" ]; then
            bootstrap_log "Removing stale bootstrap lock at ${lock_dir}"
            rm -rf "${lock_dir}" 2>/dev/null || true
            continue
        fi

        if [ $((now_ts - start_ts)) -ge "${timeout_seconds}" ]; then
            bootstrap_log "Timed out waiting for bootstrap lock at ${lock_dir}"
            return 1
        fi

        bootstrap_log "Waiting for bootstrap lock at ${lock_dir}"
        sleep "${poll_seconds}"
    done

    date +%s > "${lock_dir}/timestamp"
    printf '%s\n' "$$" > "${lock_dir}/pid"

    (
        while [ -d "${lock_dir}" ]; do
            date +%s > "${lock_dir}/timestamp" 2>/dev/null || true
            sleep "${heartbeat_seconds}"
        done
    ) &
    printf '%s\n' "$!" > "${lock_dir}/heartbeat.pid"
}

release_bootstrap_lock() {
    local lock_dir="$1"
    local heartbeat_pid=""

    if [ -f "${lock_dir}/heartbeat.pid" ]; then
        heartbeat_pid="$(cat "${lock_dir}/heartbeat.pid" 2>/dev/null || true)"
    fi

    if [ -n "${heartbeat_pid}" ]; then
        kill "${heartbeat_pid}" 2>/dev/null || true
        wait "${heartbeat_pid}" 2>/dev/null || true
    fi

    rm -rf "${lock_dir}" 2>/dev/null || true
}

seed_directory_if_missing() {
    local source_dir="$1"
    local target_dir="$2"
    local label="$3"
    local marker_file="${target_dir}/.worker-seeded"
    local source_size

    if [ -f "${marker_file}" ]; then
        bootstrap_log "Using persisted ${label} at ${target_dir}"
        return
    fi

    if [ -d "${target_dir}" ] && find "${target_dir}" -mindepth 1 -maxdepth 1 -print -quit >/dev/null 2>&1; then
        reset_incomplete_seed_directory "${target_dir}" "${label}"
    fi

    source_size="$(describe_directory_size "${source_dir}")"
    bootstrap_log "Seeding ${label} into ${target_dir} from ${source_dir} (${source_size})"
    mkdir -p "${target_dir}"
    run_with_progress_logs "Seeding ${label}" "${target_dir}" \
        cp -a "${source_dir}/." "${target_dir}/"
    touch "${marker_file}"
    bootstrap_log "${label} seed marked complete"
}

replace_with_symlink() {
    local source_path="$1"
    local target_path="$2"

    if [ -L "${source_path}" ] && [ "$(readlink "${source_path}")" = "${target_path}" ]; then
        return
    fi

    rm -rf "${source_path}"
    ln -s "${target_path}" "${source_path}"
}

sync_directory_entries_if_missing() {
    local source_dir="$1"
    local target_dir="$2"
    local label="$3"
    local entry=""
    local entry_name=""

    if [ ! -d "${source_dir}" ]; then
        return
    fi

    mkdir -p "${target_dir}"

    for entry in "${source_dir}"/*; do
        [ -e "${entry}" ] || continue
        entry_name="$(basename "${entry}")"

        if [ -e "${target_dir}/${entry_name}" ]; then
            continue
        fi

        bootstrap_log "Syncing image-baked ${label} ${entry_name} into persisted workspace"
        cp -a "${entry}" "${target_dir}/${entry_name}"
    done
}

write_extra_model_paths() {
    local base_path="$1"
    local output_file="${EXTRA_MODEL_PATHS_FILE:-/opt/venv/extra_model_paths.yaml}"

    mkdir -p "$(dirname "${output_file}")"

    cat > "${output_file}" <<EOF
bootstrap_workspace:
  base_path: ${base_path}
  checkpoints: models/checkpoints/
  clip: models/clip/
  clip_vision: models/clip_vision/
  configs: models/configs/
  controlnet: models/controlnet/
  embeddings: models/embeddings/
  latent_upscale_models: models/latent_upscale_models/
  loras: models/loras/
  text_encoders: models/text_encoders/
  diffusion_models: models/diffusion_models/
  upscale_models: models/upscale_models/
  vae: models/vae/
  unet: models/unet/
EOF
}

bootstrap_workspace() {
    local venv_image_root="${VENV_IMAGE_ROOT:-/opt/venv}"
    local venv_runtime_root="${VENV_RUNTIME_ROOT:-/opt/venv}"
    local extra_model_paths_file="${EXTRA_MODEL_PATHS_FILE:-${venv_runtime_root}/extra_model_paths.yaml}"
    local workflow_template_source_root="${WORKFLOW_TEMPLATE_SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
    local workflow_target_dir_rel="${WORKFLOW_TARGET_DIR:-user/default/workflows}"
    local workflow_target_dir=""
    local models_image_root="${MODELS_IMAGE_ROOT:-}"
    local models_runtime_root="${MODELS_RUNTIME_ROOT:-}"

    if [ "${PERSIST_WORKSPACE:-true}" != "true" ]; then
        bootstrap_log "Workspace persistence disabled"
        return
    fi

    local persistent_root
    persistent_root="$(detect_persistent_root)"

    if [ -z "${persistent_root}" ]; then
        bootstrap_log "No persistent workspace mount detected; using image-local paths"
        export PATH="${venv_runtime_root}/bin:${PATH}"
        return
    fi

    export WORKSPACE_ROOT="${persistent_root}"

    local state_root="${WORKSPACE_STATE_ROOT:-${WORKSPACE_ROOT}/worker-venv}"
    local venv_root="${state_root}/venv"
    local cache_root="${state_root}/cache"
    local bootstrap_lock_dir="${state_root}/.bootstrap.lock"

    mkdir -p \
        "${state_root}" \
        "${WORKSPACE_ROOT}/models" \
        "${cache_root}/huggingface" \
        "${cache_root}/pip" \
        "${cache_root}/torch" \
        "${cache_root}/triton" \
        "${cache_root}/xdg"

    if ! acquire_bootstrap_lock "${bootstrap_lock_dir}"; then
        bootstrap_log "Failed to acquire bootstrap lock, aborting workspace bootstrap"
        return 1
    fi

    seed_directory_if_missing "${venv_image_root}" "${venv_root}" "Python virtualenv"

    release_bootstrap_lock "${bootstrap_lock_dir}"

    replace_with_symlink "${venv_runtime_root}" "${venv_root}"

    if [ -n "${models_image_root}" ] && [ -n "${models_runtime_root}" ]; then
        replace_with_symlink "${models_runtime_root}" "${WORKSPACE_ROOT}/models"
    fi

    export PATH="${venv_runtime_root}/bin:${PATH}"
    export HF_HOME="${cache_root}/huggingface"
    export PIP_CACHE_DIR="${cache_root}/pip"
    export TORCH_HOME="${cache_root}/torch"
    export TRITON_CACHE_DIR="${cache_root}/triton"
    export XDG_CACHE_HOME="${cache_root}/xdg"


    bootstrap_log "Using persistent workspace at ${WORKSPACE_ROOT}"
    bootstrap_log "Virtualenv: ${venv_root}"
}

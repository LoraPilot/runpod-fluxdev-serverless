#!/usr/bin/env bash

set -euo pipefail

flux_log() {
    echo "worker-flux: $*"
}

flux_hf_token() {
    if [ -n "${HF_TOKEN:-}" ]; then
        printf '%s\n' "${HF_TOKEN}"
        return
    fi

    if [ -n "${HUGGINGFACE_TOKEN:-}" ]; then
        printf '%s\n' "${HUGGINGFACE_TOKEN}"
        return
    fi

    if [ -n "${HUGGINGFACE_ACCESS_TOKEN:-}" ]; then
        printf '%s\n' "${HUGGINGFACE_ACCESS_TOKEN}"
        return
    fi

    printf '%s\n' ""
}

flux_download() {
    local url="$1"
    local output_path="$2"
    local token="${3:-}"
    local backend="${FLUX_DOWNLOAD_BACKEND:-auto}"

    mkdir -p "$(dirname "${output_path}")"

    if [ -f "${output_path}" ]; then
        flux_log "Flux asset already present: ${output_path}"
        return
    fi

    case "${backend}" in
        auto)
            if python -c "import huggingface_hub" >/dev/null 2>&1; then
                flux_download_with_hf_hub "${url}" "${output_path}" "${token}"
            else
                flux_download_with_wget "${url}" "${output_path}" "${token}"
            fi
            ;;
        hf_hub)
            flux_download_with_hf_hub "${url}" "${output_path}" "${token}"
            ;;
        wget)
            flux_download_with_wget "${url}" "${output_path}" "${token}"
            ;;
        *)
            flux_log "Unsupported FLUX_DOWNLOAD_BACKEND='${backend}'"
            exit 1
            ;;
    esac
}

flux_download_with_wget() {
    local url="$1"
    local output_path="$2"
    local token="${3:-}"
    local tmp_path="${output_path}.part"
    local max_retries=3
    local retry_count=0

    flux_log "Downloading ${url##*/} to ${output_path} via wget"
    
    while [ $retry_count -lt $max_retries ]; do
        if [ -n "${token}" ]; then
            if wget -nv -c --timeout=30 --tries=2 --header="Authorization: Bearer ${token}" -O "${tmp_path}" "${url}"; then
                break
            fi
        else
            if wget -nv -c --timeout=30 --tries=2 -O "${tmp_path}" "${url}"; then
                break
            fi
        fi
        
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $max_retries ]; then
            flux_log "Download failed, retrying ($retry_count/$max_retries)..."
            sleep 2
        fi
    done
    
    if [ $retry_count -eq $max_retries ]; then
        flux_log "Failed to download ${url##*/} after $max_retries attempts"
        rm -f "${tmp_path}"
        return 1
    fi
    
    mv "${tmp_path}" "${output_path}"
    flux_log "Download completed: ${output_path}"
}

flux_download_with_hf_hub() {
    local url="$1"
    local output_path="$2"
    local token="${3:-}"

    export FLUX_DOWNLOAD_URL="${url}"
    export FLUX_DOWNLOAD_OUTPUT_PATH="${output_path}"
    export FLUX_DOWNLOAD_TOKEN="${token}"

    flux_log "Downloading ${url##*/} to ${output_path} via huggingface_hub"
    if python - <<'PY'
import os
import re
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

url = os.environ["FLUX_DOWNLOAD_URL"]
output_path = Path(os.environ["FLUX_DOWNLOAD_OUTPUT_PATH"])
token = os.environ.get("FLUX_DOWNLOAD_TOKEN") or None

match = re.match(r"^https://huggingface\.co/([^/]+/[^/]+)/resolve/([^/]+)/(.+)$", url)
if not match:
    print(f"Unsupported Hugging Face resolve URL: {url}", file=sys.stderr)
    sys.exit(1)

repo_id, revision, filename = match.groups()
output_path.parent.mkdir(parents=True, exist_ok=True)

try:
    downloaded_path = Path(
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            token=token,
            local_dir=str(output_path.parent),
            local_dir_use_symlinks=False,
        )
    )
except Exception as e:
    print(f"Download failed: {e}", file=sys.stderr)
    sys.exit(1)

if downloaded_path.resolve() != output_path.resolve():
    downloaded_path.replace(output_path)

print(f"Download completed: {output_path}")
PY
    then
        flux_log "Download completed: ${output_path}"
    else
        flux_log "Failed to download ${url##*/} via huggingface_hub"
        return 1
    fi

    unset FLUX_DOWNLOAD_URL
    unset FLUX_DOWNLOAD_OUTPUT_PATH
    unset FLUX_DOWNLOAD_TOKEN
}

bootstrap_flux() {
    local preload="${FLUX_DEV_PRELOAD:-false}"
    local model_root="${FLUX_MODEL_ROOT:-/workspace/models}"
    local diffusion_dir="${model_root}/diffusion_models"
    local text_encoder_dir="${model_root}/text_encoders"
    local vae_dir="${model_root}/vae"
    local token
    local download_errors=0
    token="$(flux_hf_token)"

    if [ "${preload}" != "true" ]; then
        flux_log "FLUX_DEV_PRELOAD is not set to true, skipping model download"
        return
    fi

    flux_log "Starting Flux model preload..."
    flux_log "Model root: ${model_root}"

    # Download Flux Dev model
    if ! flux_download \
        "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors" \
        "${diffusion_dir}/flux1-dev.safetensors" \
        "${token}"; then
        download_errors=$((download_errors + 1))
        flux_log "Failed to download Flux Dev model"
    fi

    # Download T5 text encoder (fp16 recommended for >32GB RAM, fp8 for lower memory)
    if ! flux_download \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors" \
        "${text_encoder_dir}/t5xxl_fp16.safetensors" \
        "${token}"; then
        download_errors=$((download_errors + 1))
        flux_log "Failed to download T5 text encoder"
    fi

    # Download CLIP-L text encoder
    if ! flux_download \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" \
        "${text_encoder_dir}/clip_l.safetensors" \
        "${token}"; then
        download_errors=$((download_errors + 1))
        flux_log "Failed to download CLIP-L text encoder"
    fi

    # Download VAE
    if ! flux_download \
        "https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors" \
        "${vae_dir}/ae.safetensors" \
        "${token}"; then
        download_errors=$((download_errors + 1))
        flux_log "Failed to download VAE"
    fi

    if [ $download_errors -gt 0 ]; then
        flux_log "Flux model preload completed with $download_errors error(s)"
        return 1
    fi

    flux_log "Flux model preload completed successfully."
}

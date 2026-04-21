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

    flux_log "Downloading ${url##*/} to ${output_path} via wget"
    if [ -n "${token}" ]; then
        wget -nv -c --header="Authorization: Bearer ${token}" -O "${tmp_path}" "${url}"
    else
        wget -nv -c -O "${tmp_path}" "${url}"
    fi
    mv "${tmp_path}" "${output_path}"
}

flux_download_with_hf_hub() {
    local url="$1"
    local output_path="$2"
    local token="${3:-}"

    export FLUX_DOWNLOAD_URL="${url}"
    export FLUX_DOWNLOAD_OUTPUT_PATH="${output_path}"
    export FLUX_DOWNLOAD_TOKEN="${token}"

    flux_log "Downloading ${url##*/} to ${output_path} via huggingface_hub"
    python - <<'PY'
import os
import re
from pathlib import Path

from huggingface_hub import hf_hub_download

url = os.environ["FLUX_DOWNLOAD_URL"]
output_path = Path(os.environ["FLUX_DOWNLOAD_OUTPUT_PATH"])
token = os.environ.get("FLUX_DOWNLOAD_TOKEN") or None

match = re.match(r"^https://huggingface\.co/([^/]+/[^/]+)/resolve/([^/]+)/(.+)$", url)
if not match:
    raise SystemExit(f"Unsupported Hugging Face resolve URL: {url}")

repo_id, revision, filename = match.groups()
output_path.parent.mkdir(parents=True, exist_ok=True)

downloaded_path = Path(
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
        token=token,
        local_dir=str(output_path.parent),
    )
)

if downloaded_path.resolve() != output_path.resolve():
    downloaded_path.replace(output_path)
PY

    unset FLUX_DOWNLOAD_URL
    unset FLUX_DOWNLOAD_OUTPUT_PATH
    unset FLUX_DOWNLOAD_TOKEN
}

bootstrap_flux() {
    local preload="${FLUX_DEV_PRELOAD:-false}"
    local model_root="${COMFY_MODEL_ROOT:-/workspace/models}"
    local diffusion_dir="${model_root}/diffusion_models"
    local text_encoder_dir="${model_root}/text_encoders"
    local vae_dir="${model_root}/vae"
    local token
    token="$(flux_hf_token)"

    if [ "${preload}" != "true" ]; then
        flux_log "FLUX_DEV_PRELOAD is not set to true, skipping model download"
        return
    fi

    flux_log "Starting Flux model preload..."

    # Download Flux Dev model
    flux_download \
        "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors" \
        "${diffusion_dir}/flux1-dev.safetensors" \
        "${token}"

    # Download T5 text encoder (fp16 recommended for >32GB RAM, fp8 for lower memory)
    flux_download \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors" \
        "${text_encoder_dir}/t5xxl_fp16.safetensors" \
        "${token}"

    # Download CLIP-L text encoder
    flux_download \
        "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" \
        "${text_encoder_dir}/clip_l.safetensors" \
        "${token}"

    # Download VAE
    flux_download \
        "https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors" \
        "${vae_dir}/ae.safetensors" \
        "${token}"

    flux_log "Flux model preload completed."
}

bootstrap_flux

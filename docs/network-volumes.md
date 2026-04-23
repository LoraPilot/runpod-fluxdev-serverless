# Network Volumes for FLUX.1-dev

This document explains how to use RunPod **Network Volumes** with this worker, how model paths are resolved inside the container, which worker state is persisted on the volume, and how to debug cases where models are not detected.

> **Scope**
>
> These instructions apply to **serverless endpoints** using this worker. Pods mount network volumes at `/workspace` by default. Serverless workers see the volume at `/runpod-volume`, and this worker creates a `/workspace` alias to that path so the runtime can use one internal root.

> **Important**
>
> The default worker image downloads FLUX.1-dev into `/workspace/models` at runtime. Network volumes are therefore the sane default for:
> - Persisting the Python venv and caches across worker restarts
> - Persisting the downloaded FLUX base model across worker restarts
> - Storing additional models (LoRAs, custom checkpoints, etc.)

## Directory Mapping

For **serverless endpoints**:

- Network volume root is mounted at: `/runpod-volume`
- Worker-internal persistent root is normalized to: `/workspace`
- FLUX models are therefore resolved from: `/workspace/models/...`
- This is the same storage as: `/runpod-volume/models/...`

For **Pods**:

- Network volume root is mounted at: `/workspace`
- Equivalent FLUX model path: `/workspace/models/...`

This worker also persists its runtime state under:

- `/workspace/worker-venv/venv`
- `/workspace/worker-venv/cache`
- `/workspace/worker-venv/.bootstrap.lock`

That means the Python environment and model-download caches can survive worker restarts when a network volume is attached.
The bootstrap lock is there specifically to stop multiple workers from trying to seed the same shared persisted venv at the same time.

## Path Cheat Sheet

With persistence enabled, the current runtime uses these paths:

| Purpose | Path |
| ------- | ---- |
| Persistent root | `/workspace` |
| Serverless mount backing that root | `/runpod-volume` |
| Persisted Python venv | `/workspace/worker-venv/venv` |
| Persisted caches | `/workspace/worker-venv/cache` |
| Shared bootstrap lock | `/workspace/worker-venv/.bootstrap.lock` |
| Shared model root | `/workspace/models` |

If you use the S3-compatible API, the same paths map as:

- Serverless: `/runpod-volume/my-folder/file.txt`
- Pod: `/workspace/my-folder/file.txt`
- S3 API: `s3://<NETWORK_VOLUME_ID>/my-folder/file.txt`

## Expected Directory Structure

The worker expects a **diffusers snapshot** rooted at `/workspace/models`:

```text
/workspace/
└── models/
    ├── model_index.json
    ├── scheduler/
    ├── text_encoder/
    ├── text_encoder_2/
    ├── tokenizer/
    ├── tokenizer_2/
    ├── transformer/
    └── vae/
```

On serverless, `/workspace/models/...` and `/runpod-volume/models/...` are the same underlying storage.

The runtime preload path in this repo downloads exactly that structure on first boot when `FLUX_DEV_PRELOAD=true` and a Hugging Face token is present.

## Detection Rules

The worker considers a local model path valid when it finds diffusers metadata at the root, specifically `model_index.json` or `config.json`.

## Common Issues

- **Wrong root directory**
  - Diffusers files placed directly under `/runpod-volume/...` instead of `/runpod-volume/models/...`.
- **Incomplete diffusers snapshot**
  - `model_index.json` is missing, or one of the required component folders is absent.
- **Missing Hugging Face token**
  - `FLUX_DEV_PRELOAD=true` is set, but no `HUGGINGFACE_ACCESS_TOKEN`, `HUGGINGFACE_TOKEN`, or `HF_TOKEN` is available.
- **Volume not attached**
  - Endpoint created without selecting a network volume under **Advanced → Select Network Volume**.

If any of the above is true, the model discovery will fail.

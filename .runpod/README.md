---

Run [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) text-to-image generation as a RunPod serverless endpoint with Redis caching.

---

Use the hub metadata in `.runpod/hub.json` when publishing this template to RunPod Hub.

---

## What is included?

- FLUX.1-dev text-to-image generation using FluxPipeline from diffusers
- FLUX.1-dev model baked into the Docker image in diffusers format
- Redis caching for prompt deduplication
- CUDA 12.8 as the default track, with an experimental CUDA 13 path for newer Blackwell-oriented hosts
- Persistent `/workspace` for Python venv and cache persistence

## Recommended deployment shape

- Attach a network volume. Without it, cold starts will repeatedly redownload large model assets.
- Keep `PERSIST_WORKSPACE=true`.
- Use at least 12 GB VRAM for practical FLUX.1-dev usage.
- Plan for roughly 20 GB or more of disk for model assets.

## Important environment variables

- `REDIS_URL`: Redis connection URL for caching (default: redis://localhost:6379)
- `PERSIST_WORKSPACE`: Enable persistent `/workspace` for Python venv and cache persistence (default: true)

## Usage

Send text prompts to the RunPod `/run` or `/runsync` endpoint with generation parameters.

Example payload:
```json
{
  "input": {
    "prompt": "A futuristic city at sunset, cinematic lighting",
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 50,
    "guidance_scale": 3.5
  }
}
```

The full API payload format and deployment notes live in the main project docs:

- [Repository README](https://github.com/vavo/flux-dev-serverless/blob/main/README.md)
- [Deployment Guide](https://github.com/vavo/flux-dev-serverless/blob/main/docs/deployment.md)
- [Network Volume Notes](https://github.com/vavo/flux-dev-serverless/blob/main/docs/network-volumes.md)

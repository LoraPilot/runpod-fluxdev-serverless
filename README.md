# FLUX.1-dev Serverless Worker

Serverless FLUX.1-dev text-to-image generation with Redis caching, minus the goldfish-memory cold start.

This repo turns FLUX.1-dev into a RunPod serverless template that keeps its brain on `/workspace`: Python venv, caches, and downloaded model assets survive worker churn instead of being painfully rediscovered on every boot.

Less boot drama. More actual inference.

<p align="center">
  <img src="assets/worker_sitting_in_comfy_chair.jpg" title="Worker sitting in comfy chair" />
</p>

## Quickstart

The simplest way to get started is to pull one of the pre-built Docker images from Docker Hub and deploy it as a RunPod serverless endpoint.

1. Pull a pre-built Docker image from Docker Hub.
2. Create a RunPod serverless template that uses that image.
3. Attach a network volume so `/workspace` is persistent.
4. Deploy the endpoint with `Active Workers = 0` unless you enjoy paying for idle GPUs.
5. Set at least:
   - `PERSIST_WORKSPACE=true`
   - `FLUX_DEV_PRELOAD=true`
   - `HUGGINGFACE_ACCESS_TOKEN=<your_hf_read_token>`
6. Send requests to the endpoint with a text prompt.

For detailed deployment steps, see [Deployment Guide](docs/deployment.md).

## Available Docker Images

| Target | Use Case |
| --- | --- |
| `base` | Default clean CUDA 12.8 / cu128 base image |
| `flux-dev` | Default target for CUDA 12.8 deployments with FLUX.1-dev preloaded |
| `flux-dev-cuda13` | Experimental CUDA 13 path with FLUX.1-dev preloaded |
| `base-cuda12-8-1` | Explicit CUDA 12.8 base image alias for custom builds |
| `base-cuda13-0` | Clean CUDA 13 base image for custom experimental builds |

Example image tags (replace `<repo>` and `<version>` with your values):
- `<repo>:<version>-base`
- `<repo>:<version>-flux-dev-cu128`
- `<repo>:<version>-flux-dev-cu130`

Hardware requirements: 12GB+ VRAM and 16GB+ free disk recommended. See [Deployment Guide](docs/deployment.md) for details.

## API Specification

### Input Format

```json
{
  "input": {
    "prompt": "A futuristic city at sunset, cinematic lighting",
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 50,
    "guidance_scale": 3.5,
    "seed": 42
  }
}
```

### Output Format

```json
{
  "status": "success",
  "image": "base64_encoded_png_data",
  "metadata": {
    "generation_time_sec": 12.5,
    "seed": 42
  },
  "cached": false
}
```

## Essential Configuration

### Recommended First Boot Env

For a sane first boot on RunPod serverless, use:

```env
PERSIST_WORKSPACE=true
FLUX_DEV_PRELOAD=true
HUGGINGFACE_ACCESS_TOKEN=hf_xxx
REDIS_URL=redis://localhost:6379
```

This preloads the FLUX.1-dev model into persistent storage. Some secondary assets may still download on first render.

For the full list of environment variables, see [Configuration Guide](docs/configuration.md).

## Documentation

- [Deployment Guide](docs/deployment.md) - Detailed RunPod template/endpoint creation, GPU recommendations
- [Configuration Guide](docs/configuration.md) - Comprehensive list and explanation of all environment variables
- [Customization Guide](docs/customization.md) - In-depth guide on using Network Volumes and building custom Docker images
- [Network Volumes & Model Paths](docs/network-volumes.md) - How to use network volumes and debug model detection issues
- [Development Guide](docs/development.md) - Instructions for local setup, running tests, using docker-compose
- [CI/CD Guide](docs/ci-cd.md) - Explanation of the GitHub Actions workflows for Docker Hub deployment
- [Conventions](docs/conventions.md) - Project conventions and rules for development
- [Acknowledgments](docs/acknowledgments.md) - Credits and thanks

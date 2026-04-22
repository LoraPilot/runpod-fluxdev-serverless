# FLUX.1-dev Serverless Worker

Serverless FLUX.1-dev text-to-image generation with Redis caching, minus the goldfish-memory cold start.

This repo turns FLUX.1-dev into a RunPod serverless template that keeps its brain on `/workspace`: Python venv, caches, and downloaded model assets survive worker churn instead of being painfully rediscovered on every boot.

Less boot drama. More actual inference.


## Quickstart

The simplest way to get started is to pull a pre-built Docker image from Docker Hub and deploy it as a RunPod serverless endpoint.

Pre-built images include both the FLUX.1-dev handler and the model in diffusers format.

1. Pull a pre-built Docker image from Docker Hub.
2. Create a RunPod serverless template that uses that image.
3. Attach a network volume so `/workspace` is persistent (optional but recommended).
4. Deploy the endpoint with `Active Workers = 0` unless you enjoy paying for idle GPUs.
5. Send requests to the endpoint with a text prompt.

For detailed deployment steps, see [Deployment Guide](docs/deployment.md).

> **Note:** If you need to build the image yourself (instead of using pre-built images), you can optionally provide `HUGGINGFACE_ACCESS_TOKEN` as a build argument to bake the model into the image. Without the token, the model will be downloaded at runtime from HuggingFace:
> ```bash
> # Build with model baked in (requires HuggingFace access token)
> docker build --build-arg HUGGINGFACE_ACCESS_TOKEN=hf_xxx --platform linux/amd64 -t flux-dev-worker:latest .
>
> # Build without model (downloads at runtime)
> docker build --platform linux/amd64 -t flux-dev-worker:latest .
> ```

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
HUGGINGFACE_ACCESS_TOKEN=hf_xxx
REDIS_URL=redis://localhost:6379
```

The FLUX.1-dev model is included in the Docker image, so no preload is needed. Workspace persistence caches Python venv and other assets across worker restarts.

For the full list of environment variables, see [Configuration Guide](docs/configuration.md).

## Testing the Endpoint

### Local Testing

You can test the endpoint locally using `docker-compose`:

```bash
docker-compose up --build
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "A futuristic city at sunset, cinematic lighting",
      "width": 1024,
      "height": 1024,
      "num_inference_steps": 50,
      "guidance_scale": 3.5,
      "seed": 42
    }
  }'
```

### Sample API Response

```json
{
  "status": "success",
  "image": "iVBORw0KGgoAAAANSUhEUgAA...<truncated base64 PNG data>...A5ElFTkSuQmCC",
  "metadata": {
    "generation_time_sec": 12.5,
    "seed": 42
  },
  "cached": false
}
```

The `image` field contains a base64-encoded PNG image. Decode it to view or save the generated image:

```bash
echo "iVBORw0KGgoAAAANSUhEUgAA..." | base64 -d > output.png
```

### RunPod Serverless Testing

For a deployed RunPod serverless endpoint, use your endpoint URL and API key:

```bash
curl -X POST https://api.runpod.ai/v2/<endpoint_id>/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api_key>" \
  -d '{
    "input": {
      "prompt": "A futuristic city at sunset, cinematic lighting",
      "width": 1024,
      "height": 1024,
      "num_inference_steps": 50,
      "guidance_scale": 3.5,
      "seed": 42
    }
  }'
```

## Documentation

- [Deployment Guide](docs/deployment.md) - Detailed RunPod template/endpoint creation, GPU recommendations
- [Configuration Guide](docs/configuration.md) - Comprehensive list and explanation of all environment variables
- [Customization Guide](docs/customization.md) - In-depth guide on using Network Volumes and building custom Docker images
- [Network Volumes & Model Paths](docs/network-volumes.md) - How to use network volumes and debug model detection issues
- [Development Guide](docs/development.md) - Instructions for local setup, running tests, using docker-compose
- [CI/CD Guide](docs/ci-cd.md) - Explanation of the GitHub Actions workflows for Docker Hub deployment
- [Conventions](docs/conventions.md) - Project conventions and rules for development
- [Acknowledgments](docs/acknowledgments.md) - Credits and thanks

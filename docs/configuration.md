# Configuration

This document outlines the environment variables available for configuring the worker.

## General Configuration

| Environment Variable | Description                                                                                                                                                                                                                  | Default |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `REFRESH_WORKER`     | When `true`, the worker pod will stop after each completed job to ensure a clean state for the next job. See the [RunPod documentation](https://docs.runpod.io/docs/handler-additional-controls#refresh-worker) for details. | `false` |
| `RUN_MODE` | Container startup mode: `worker` or `local-api`. | `worker` |
| `SERVE_API_LOCALLY`  | Legacy compatibility flag. When `RUN_MODE` is unset and this is `true`, startup falls back to `local-api`. See the [Development Guide](development.md#local-api-simulation-using-docker-compose) for more details. | `false` |
| `PERSIST_WORKSPACE`  | When `true`, persist the Python venv, caches, and downloaded assets under `/workspace` (which aliases `/runpod-volume` on serverless).                                                                            | `true`  |
| `WORKSPACE_ROOT`     | Override the detected persistent workspace root. Useful only if your mount layout differs from RunPod defaults.                                                                                                              | auto    |
| `WORKSPACE_STATE_ROOT` | Override the state directory inside the persistent workspace.                                                                                                                         | `/workspace/worker-venv` |
| `HUGGINGFACE_ACCESS_TOKEN` | Optional token used when the base model is not baked into the image and the worker must download it at startup. `HF_TOKEN` and `HUGGINGFACE_TOKEN` are also accepted aliases by the preload script. | – |
| `FLUX_MODEL_PATH` | Optional override for the local diffusers model directory. If unset, the worker prefers a valid `/workspace/models` copy and otherwise falls back to the baked image copy under `/opt/models/FLUX.1-dev`. | auto |
| `REDIS_URL` | Redis connection used for successful response caching. If Redis is unavailable, the worker still runs and simply skips cache reads and writes. | `redis://localhost:6379` |
| `CACHE_TTL_SECONDS` | How long successful cached responses stay in Redis. | `604800` |

## Bootstrap Locking

When multiple workers share the same persisted `/workspace`, the bootstrap now uses a shared lock at `/workspace/worker-venv/.bootstrap.lock` while seeding the persisted Python virtualenv.

That prevents concurrent first-boot workers from trampling the same shared venv. If a worker dies while holding the lock, stale-lock cleanup will eventually remove it.

## Recommended First Boot

For the least annoying first worker boot on RunPod serverless, set:

```env
PERSIST_WORKSPACE=true
RUN_MODE=worker
REDIS_URL=redis://localhost:6379
```

The FLUX.1-dev model is already included in the Docker image in diffusers format. No runtime preload is needed. Workspace persistence caches Python venv and other assets across worker restarts.

## Runtime Paths

With workspace persistence enabled, the worker uses these paths:

| Purpose | Path |
| ------- | ---- |
| Persistent root | `/workspace` |
| Python virtualenv | `/workspace/worker-venv/venv` |
| Download and compiler caches | `/workspace/worker-venv/cache` |
| Shared bootstrap lock | `/workspace/worker-venv/.bootstrap.lock` |
| Shared model root for runtime preload or custom overrides | `/workspace/models` |
| Image-baked base FLUX model | `/opt/models/FLUX.1-dev` |

On serverless, `/workspace` is the worker's internal alias for `/runpod-volume`.

## Logging Configuration

| Environment Variable   | Description                                                                                                                                                      | Default |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `NETWORK_VOLUME_DEBUG` | Enable detailed network volume diagnostics in worker logs. Useful for debugging model path issues. See [Network Volumes & Model Paths](network-volumes.md).      | `false` |

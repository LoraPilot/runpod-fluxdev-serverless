# ==============================================================================
# FLUX.1-dev Serverless Handler
# Text-to-Image Generation using FluxPipeline with Redis Caching
# ==============================================================================

import runpod
import base64
import io
import json
import os
import time
import uuid
import logging
import hashlib
import random
from pathlib import Path
from typing import Any

import redis
import torch
from diffusers import FluxPipeline

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}')
logger = logging.getLogger("FluxHandler")

# --- Configuration ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "604800"))
MODEL_PATH = os.environ.get("FLUX_MODEL_PATH", "/workspace/models/diffusion_models/flux1-dev.safetensors")

# --- Redis Client ---
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, retry_on_timeout=True)
    logger.info("Connected to Redis")
except Exception as e:
    logger.warning(f"Failed to connect to Redis: {e}. Caching will be disabled.")
    redis_client = None

# --- Global Pipeline (lazy loaded) ---
_flux_pipeline = None


def get_flux_pipeline():
    """Lazy load FluxPipeline on first request."""
    global _flux_pipeline
    if _flux_pipeline is not None:
        return _flux_pipeline
    
    logger.info("Loading FluxPipeline...")
    try:
        # Load from persistent storage or HuggingFace
        if os.path.exists(MODEL_PATH):
            logger.info(f"Loading Flux model from {MODEL_PATH}")
            _flux_pipeline = FluxPipeline.from_pretrained(
                "/workspace/models",
                torch_dtype=torch.bfloat16,
                use_safetensors=True
            )
        else:
            logger.info("Loading Flux model from HuggingFace")
            _flux_pipeline = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-dev",
                torch_dtype=torch.bfloat16
            )
        
        # Enable CPU offload if GPU memory is limited
        _flux_pipeline.enable_model_cpu_offload()
        logger.info("FluxPipeline loaded successfully")
        return _flux_pipeline
    except Exception as e:
        logger.error(f"Failed to load FluxPipeline: {e}")
        raise


def decode_cached_response(raw_value: str) -> dict | None:
    try:
        cached_response = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None

    if not isinstance(cached_response, dict) or cached_response.get("status") != "success":
        return None

    response = dict(cached_response)
    response["cached"] = True
    return response


def build_cache_key(prompt: str, width: int, height: int, num_inference_steps: int, guidance_scale: float) -> str:
    """Build a cache key from generation parameters."""
    params = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
    }
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def image_to_base64(image) -> str:
    """Convert PIL image to base64 string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def handler(job: dict) -> dict:
    """RunPod serverless handler for FLUX.1-dev text-to-image generation."""
    job_id = job.get('id', uuid.uuid4().hex)
    job_input = job.get('input', {})
    start_time = time.time()
    
    # Extract parameters
    prompt = job_input.get("prompt", "")
    if not prompt:
        return {"status": "error", "error": "Missing 'prompt' parameter"}
    
    width = job_input.get("width", 1024)
    height = job_input.get("height", 1024)
    num_inference_steps = job_input.get("num_inference_steps", 50)
    guidance_scale = job_input.get("guidance_scale", 3.5)
    seed = job_input.get("seed", random.randint(0, 2**32 - 1))
    
    # Validate parameters
    if not isinstance(width, int) or width < 512 or width > 2048:
        return {"status": "error", "error": "width must be between 512 and 2048"}
    if not isinstance(height, int) or height < 512 or height > 2048:
        return {"status": "error", "error": "height must be between 512 and 2048"}
    if not isinstance(num_inference_steps, int) or num_inference_steps < 10 or num_inference_steps > 100:
        return {"status": "error", "error": "num_inference_steps must be between 10 and 100"}
    if not isinstance(guidance_scale, (int, float)) or guidance_scale < 1.0 or guidance_scale > 10.0:
        return {"status": "error", "error": "guidance_scale must be between 1.0 and 10.0"}
    
    logger.info(f"[{job_id}] Processing prompt: {prompt[:100]}...")
    
    # Check Redis cache
    cache_key = build_cache_key(prompt, width, height, num_inference_steps, guidance_scale)
    if redis_client:
        try:
            cached_response = decode_cached_response(redis_client.get(cache_key))
            if cached_response:
                logger.info(f"[{job_id}] Cache hit for key: {cache_key[:16]}...")
                return cached_response
        except Exception as e:
            logger.warning(f"[{job_id}] Redis cache check failed: {e}")
    
    # Generate image
    try:
        pipeline = get_flux_pipeline()
        
        generator = torch.Generator("cpu").manual_seed(seed)
        
        image = pipeline(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
            max_sequence_length=512,
        ).images[0]
        
        # Convert to base64
        image_base64 = image_to_base64(image)
        
        generation_time = round(time.time() - start_time, 2)
        logger.info(f"[{job_id}] Image generated in {generation_time}s")
        
        response = {
            "status": "success",
            "image": image_base64,
            "metadata": {
                "generation_time_sec": generation_time,
                "seed": seed,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
            },
        }
        
        # Cache response
        if redis_client:
            try:
                redis_client.set(cache_key, json.dumps(response), ex=CACHE_TTL_SECONDS)
                logger.info(f"[{job_id}] Response cached")
            except Exception as e:
                logger.warning(f"[{job_id}] Failed to cache response: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"[{job_id}] Generation failed: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    logger.info("Starting FLUX.1-dev Serverless Handler...")
    runpod.serverless.start({"handler": handler})

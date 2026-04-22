# ==============================================================================
# FLUX.1-dev Serverless Handler
# Text-to-Image Generation using FluxPipeline with Redis Caching
# =============================================================================

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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from contextlib import contextmanager
from functools import wraps

import redis
import torch
from diffusers import FluxPipeline

# --- Logging ---
class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "N/A"),
        }
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        return json.dumps(log_data)

logging.basicConfig(level=logging.INFO, format='%(message)s')
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("FluxHandler")
logger.addHandler(handler)
logger.propagate = False


def with_request_id(func):
    """Decorator to add request_id to log records."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        request_id = kwargs.get('job_id') or str(uuid.uuid4())[:8]
        logger_adapter = logging.LoggerAdapter(logger, {"request_id": request_id})
        return func(*args, **kwargs, logger=logger_adapter)
    return wrapper


@contextmanager
def performance_monitor(operation: str, logger: logging.LoggerAdapter):
    """Context manager for performance monitoring."""
    start_time = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        logger.info(f"{operation} completed", extra={"operation": operation, "duration_sec": round(elapsed, 3)})


# --- Configuration ---
@dataclass
class HandlerConfig:
    """Configuration for the FLUX handler."""
    redis_url: str
    cache_ttl_seconds: int
    model_path: str
    max_width: int = 2048
    min_width: int = 512
    max_height: int = 2048
    min_height: int = 512
    max_inference_steps: int = 100
    min_inference_steps: int = 10
    max_guidance_scale: float = 10.0
    min_guidance_scale: float = 1.0
    
    @classmethod
    def from_env(cls) -> "HandlerConfig":
        """Load configuration from environment variables."""
        return cls(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
            cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", "604800")),
            model_path=os.environ.get("FLUX_MODEL_PATH", ""),
        )


config = HandlerConfig.from_env()

# --- Redis Client ---
redis_client: Optional[redis.Redis] = None
try:
    redis_client = redis.from_url(
        config.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        retry_on_error=[redis.ConnectionError, redis.TimeoutError],
        health_check_interval=30,
    )
    redis_client.ping()
    logger.info("Connected to Redis")
except Exception as e:
    logger.warning(f"Failed to connect to Redis: {e}. Caching will be disabled.")
    redis_client = None

# --- Global Pipeline (lazy loaded) ---
_flux_pipeline = None
MODEL_MARKER_FILES = ("model_index.json", "config.json")
WORKSPACE_MODEL_PATH = "/workspace/models"
IMAGE_MODEL_PATH = "/opt/models/FLUX.1-dev"


def is_diffusers_model_dir(path: str) -> bool:
    if not path:
        return False

    model_dir = Path(path)
    if not model_dir.is_dir():
        return False

    return any((model_dir / marker).is_file() for marker in MODEL_MARKER_FILES)


def resolve_model_path(logger: logging.LoggerAdapter) -> str | None:
    candidates: list[tuple[str, str]] = []
    seen_paths: set[str] = set()

    if config.model_path:
        candidates.append(("FLUX_MODEL_PATH", config.model_path))

    candidates.extend(
        [
            ("workspace", WORKSPACE_MODEL_PATH),
            ("image", IMAGE_MODEL_PATH),
        ]
    )

    for source_name, candidate_path in candidates:
        normalized_path = os.path.abspath(candidate_path)
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)

        if is_diffusers_model_dir(candidate_path):
            logger.info(f"Using {source_name} FLUX model at {candidate_path}")
            return candidate_path

        if Path(candidate_path).exists():
            logger.warning(
                f"Ignoring {source_name} model path {candidate_path}: missing diffusers metadata "
                f"({', '.join(MODEL_MARKER_FILES)})"
            )

    return None


def get_flux_pipeline(logger: logging.LoggerAdapter) -> FluxPipeline:
    """Lazy load FluxPipeline on first request.
    
    Args:
        logger: Logger adapter with request context
        
    Returns:
        Loaded FluxPipeline instance
    """
    global _flux_pipeline
    if _flux_pipeline is not None:
        return _flux_pipeline
    
    logger.info("Loading FluxPipeline...")
    with performance_monitor("model_loading", logger):
        try:
            local_model_path = resolve_model_path(logger)

            if local_model_path:
                logger.info(f"Loading Flux model from {local_model_path}")
                _flux_pipeline = FluxPipeline.from_pretrained(
                    local_model_path,
                    torch_dtype=torch.bfloat16,
                    use_safetensors=True
                )
            else:
                logger.info("No valid local diffusers model found; loading Flux model from HuggingFace")
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


def image_to_base64(image: Any) -> str:
    """Convert PIL image to base64 string.
    
    Args:
        image: PIL Image object
        
    Returns:
        Base64 encoded PNG string
    """
    buffered = io.BytesIO()
    image.save(buffered, format="PNG", optimize=True)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def validate_generation_params(params: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate generation parameters.
    
    Args:
        params: Dictionary of generation parameters
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    width = params.get("width", 1024)
    height = params.get("height", 1024)
    num_inference_steps = params.get("num_inference_steps", 50)
    guidance_scale = params.get("guidance_scale", 3.5)
    
    if not isinstance(width, int) or width < config.min_width or width > config.max_width:
        return False, f"width must be between {config.min_width} and {config.max_width}"
    if not isinstance(height, int) or height < config.min_height or height > config.max_height:
        return False, f"height must be between {config.min_height} and {config.max_height}"
    if not isinstance(num_inference_steps, int) or num_inference_steps < config.min_inference_steps or num_inference_steps > config.max_inference_steps:
        return False, f"num_inference_steps must be between {config.min_inference_steps} and {config.max_inference_steps}"
    if not isinstance(guidance_scale, (int, float)) or guidance_scale < config.min_guidance_scale or guidance_scale > config.max_guidance_scale:
        return False, f"guidance_scale must be between {config.min_guidance_scale} and {config.max_guidance_scale}"
    
    return True, None


def handler(job: dict[str, Any]) -> dict[str, Any]:
    """RunPod serverless handler for FLUX.1-dev text-to-image generation.
    
    Args:
        job: RunPod job dictionary containing input parameters
        
    Returns:
        Response dictionary with status, image, and metadata
    """
    job_id = job.get('id', uuid.uuid4().hex)
    job_input = job.get('input', {})
    
    # Set up logger with request context
    logger_adapter = logging.LoggerAdapter(logger, {"request_id": job_id[:8]})
    start_time = time.time()
    
    # Extract parameters
    prompt = job_input.get("prompt", "")
    if not prompt:
        logger_adapter.warning("Missing 'prompt' parameter")
        return {"status": "error", "error": "Missing 'prompt' parameter"}
    
    # Sanitize prompt
    prompt = prompt.strip()[:2000]  # Limit prompt length
    
    width = job_input.get("width", 1024)
    height = job_input.get("height", 1024)
    num_inference_steps = job_input.get("num_inference_steps", 50)
    guidance_scale = job_input.get("guidance_scale", 3.5)
    seed = job_input.get("seed", random.randint(0, 2**32 - 1))
    
    # Validate parameters
    is_valid, error_msg = validate_generation_params({
        "width": width,
        "height": height,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
    })
    if not is_valid:
        logger_adapter.warning(f"Validation failed: {error_msg}")
        return {"status": "error", "error": error_msg}
    
    logger_adapter.info(f"Processing prompt: {prompt[:100]}...", extra={"prompt_length": len(prompt)})
    
    # Check Redis cache
    cache_key = build_cache_key(prompt, width, height, num_inference_steps, guidance_scale)
    if redis_client:
        try:
            with performance_monitor("cache_lookup", logger_adapter):
                cached_response = decode_cached_response(redis_client.get(cache_key))
                if cached_response:
                    logger_adapter.info(f"Cache hit for key: {cache_key[:16]}...")
                    return cached_response
        except Exception as e:
            logger_adapter.warning(f"Redis cache check failed: {e}")
    
    # Generate image
    try:
        pipeline = get_flux_pipeline(logger_adapter)
        
        generator = torch.Generator("cpu").manual_seed(seed)
        
        with performance_monitor("image_generation", logger_adapter):
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
        with performance_monitor("image_encoding", logger_adapter):
            image_base64 = image_to_base64(image)
        
        generation_time = round(time.time() - start_time, 2)
        logger_adapter.info(f"Image generated in {generation_time}s", extra={"generation_time_sec": generation_time})
        
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
                with performance_monitor("cache_write", logger_adapter):
                    redis_client.setex(cache_key, config.cache_ttl_seconds, json.dumps(response))
                logger_adapter.info(f"Response cached with TTL {config.cache_ttl_seconds}s")
            except Exception as e:
                logger_adapter.warning(f"Failed to cache response: {e}")
        
        return response
        
    except Exception as e:
        logger_adapter.error(f"Generation failed: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    logger.info("Starting FLUX.1-dev Serverless Handler...")
    runpod.serverless.start({"handler": handler})

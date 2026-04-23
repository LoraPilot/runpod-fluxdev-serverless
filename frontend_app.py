from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.responses import Response

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
logger = logging.getLogger("FrontendApp")
logger.addHandler(handler)
logger.propagate = False


@contextmanager
def performance_monitor(operation: str, request_id: str):
    """Context manager for performance monitoring."""
    start_time = asyncio.get_event_loop().time()
    try:
        yield
    finally:
        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"{operation} completed", extra={"operation": operation, "duration_sec": round(elapsed, 3), "request_id": request_id})

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"

# Flux configuration
ASPECT_RATIOS = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1344, "height": 768},
    "9:16": {"width": 768, "height": 1344},
    "4:3": {"width": 1152, "height": 896},
    "3:4": {"width": 896, "height": 1152},
}

RUNPOD_PENDING_STATUSES = {"IN_QUEUE", "IN_PROGRESS"}
RUNPOD_FAILURE_STATUSES = {"FAILED", "ERROR", "CANCELLED", "TIMED_OUT"}
RUNPOD_POLL_INTERVAL_SECONDS = 2

app = FastAPI(title="FLUX.1-dev Image Generator")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    """Add request ID to all requests for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def disable_frontend_caching(request: Request, call_next) -> Response:
    """Disable caching for frontend assets."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class PayloadRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    width: int = Field(default=1024, ge=512, le=2048)
    height: int = Field(default=1024, ge=512, le=2048)
    aspect_ratio: str = Field(default="1:1")
    num_inference_steps: int = Field(default=50, ge=10, le=100)
    guidance_scale: float = Field(default=3.5, ge=1.0, le=10.0)
    seed: int = Field(default=0, ge=0)


class SubmitRequest(BaseModel):
    endpoint_url: str = Field(..., min_length=1)
    auth_token: str = ""
    payload: dict[str, Any]
    timeout_seconds: int = Field(default=300, ge=5, le=3600)

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("Endpoint URL must start with http:// or https://")
        return normalized


def build_runpod_status_url(endpoint_url: str, job_id: str) -> str:
    normalized = endpoint_url.rstrip("/")
    if normalized.endswith("/run") or normalized.endswith("/runsync"):
        normalized = normalized.rsplit("/", 1)[0]
    return f"{normalized}/status/{job_id}"


def build_image_data_url(image_base64: str) -> str:
    return f"data:image/png;base64,{image_base64}"


def extract_image_result(response_json: Any) -> dict[str, Any] | None:
    if not isinstance(response_json, dict):
        return None

    candidate = response_json
    output = response_json.get("output")
    if isinstance(output, dict):
        candidate = output

    image_base64 = candidate.get("image")
    image_data_url = candidate.get("image_data_url")
    if not image_data_url and image_base64:
        image_data_url = build_image_data_url(image_base64)

    if not image_base64 and not image_data_url:
        return None

    return {
        "image_base64": image_base64,
        "image_data_url": image_data_url,
        "metadata": candidate.get("metadata"),
        "output_status": candidate.get("status"),
    }


def extract_error_message(response_json: Any, response_text: str | None = None) -> str | None:
    if isinstance(response_json, dict):
        if isinstance(response_json.get("error"), str):
            return response_json["error"]
        output = response_json.get("output")
        if isinstance(output, dict) and isinstance(output.get("error"), str):
            return output["error"]
        if isinstance(response_json.get("message"), str):
            return response_json["message"]
    if response_text:
        return response_text
    return None


def build_submit_result(
    *,
    status_code: int,
    content_type: str,
    endpoint_url: str,
    response_json: Any | None,
    response_text: str | None,
) -> dict[str, object]:
    image_result = extract_image_result(response_json)
    job_status = response_json.get("status") if isinstance(response_json, dict) else None
    output_status = image_result.get("output_status") if image_result else None

    ok = 200 <= status_code < 300
    if job_status in RUNPOD_FAILURE_STATUSES or output_status == "error":
        ok = False

    return {
        "ok": ok,
        "status_code": status_code,
        "content_type": content_type or "application/octet-stream",
        "endpoint_url": endpoint_url,
        "job_id": response_json.get("id") if isinstance(response_json, dict) else None,
        "job_status": job_status,
        "response_json": response_json,
        "response_text": None if response_json is not None else response_text,
        "image_base64": image_result.get("image_base64") if image_result else None,
        "image_data_url": image_result.get("image_data_url") if image_result else None,
        "metadata": image_result.get("metadata") if image_result else None,
        "error_message": extract_error_message(response_json, response_text),
    }




@app.get("/", response_class=FileResponse)
async def index(request: Request) -> FileResponse:
    request_id = request.headers.get("X-Request-ID", "N/A")
    logger.info("Serving index page", extra={"request_id": request_id})
    return FileResponse(FRONTEND_DIR / "index.html")




@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    request_id = request.headers.get("X-Request-ID", "N/A")
    logger.info("Health check", extra={"request_id": request_id})
    return {"status": "ok"}


@app.get("/api/config")
async def config(request: Request) -> dict[str, object]:
    request_id = request.headers.get("X-Request-ID", "N/A")
    logger.info("Fetching config", extra={"request_id": request_id})
    return {
        "width": {"min": 512, "max": 2048, "default": 1024, "step": 64},
        "height": {"min": 512, "max": 2048, "default": 1024, "step": 64},
        "num_inference_steps": {"min": 10, "max": 100, "default": 50},
        "guidance_scale": {"min": 1.0, "max": 10.0, "default": 3.5, "step": 0.5},
        "aspect_ratios": ASPECT_RATIOS,
    }


@app.post("/api/payload")
async def create_payload(request: PayloadRequest, http_request: Request) -> dict[str, object]:
    request_id = http_request.headers.get("X-Request-ID", "N/A")
    logger.info("Creating payload", extra={"request_id": request_id, "prompt_length": len(request.prompt)})
    
    # Apply aspect ratio if specified
    if request.aspect_ratio in ASPECT_RATIOS:
        dimensions = ASPECT_RATIOS[request.aspect_ratio]
        width = dimensions["width"]
        height = dimensions["height"]
    else:
        width = request.width
        height = request.height
    
    input_payload = {
        "prompt": request.prompt,
        "width": width,
        "height": height,
        "num_inference_steps": request.num_inference_steps,
        "guidance_scale": request.guidance_scale,
        "include_image_data_url": True,
    }
    if request.seed > 0:
        input_payload["seed"] = request.seed

    payload = {"input": input_payload}

    return {
        "payload": payload,
        "summary": {
            "width": width,
            "height": height,
            "aspect_ratio": request.aspect_ratio,
            "num_inference_steps": request.num_inference_steps,
            "guidance_scale": request.guidance_scale,
            "seed": request.seed if request.seed > 0 else None,
        },
    }


@app.post("/api/submit")
async def submit_payload(request: SubmitRequest, http_request: Request) -> dict[str, object]:
    request_id = http_request.headers.get("X-Request-ID", "N/A")
    logger.info("Submitting payload", extra={"request_id": request_id, "endpoint_url": request.endpoint_url})
    
    headers = {"Content-Type": "application/json"}
    auth_token = request.auth_token.strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    timeout = aiohttp.ClientTimeout(total=min(request.timeout_seconds, 30))
    deadline = asyncio.get_event_loop().time() + request.timeout_seconds

    try:
        with performance_monitor("submit_request", request_id):
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    request.endpoint_url,
                    json=request.payload,
                    headers=headers,
                ) as response:
                    raw_body = await response.text()
                    content_type = response.headers.get("Content-Type", "")
                    response_json: Any | None = None

                    if "json" in content_type.lower():
                        try:
                            response_json = json.loads(raw_body)
                        except json.JSONDecodeError:
                            response_json = None

                    final_status_code = response.status
                    final_content_type = content_type
                    final_response_json = response_json
                    final_response_text = None if response_json is not None else raw_body

                    if (
                        isinstance(response_json, dict)
                        and response_json.get("status") in RUNPOD_PENDING_STATUSES
                        and response_json.get("id")
                    ):
                        job_id = response_json["id"]
                        status_url = build_runpod_status_url(request.endpoint_url, job_id)
                        logger.info(
                            f"Polling RunPod job status at {status_url}",
                            extra={"request_id": request_id, "job_id": job_id},
                        )

                        while True:
                            remaining = deadline - asyncio.get_event_loop().time()
                            if remaining <= 0:
                                raise HTTPException(status_code=504, detail="Timed out while waiting for the RunPod job to finish.")

                            await asyncio.sleep(min(RUNPOD_POLL_INTERVAL_SECONDS, max(0.1, remaining)))

                            async with session.get(status_url, headers=headers) as status_response:
                                final_status_code = status_response.status
                                final_content_type = status_response.headers.get("Content-Type", "")
                                status_body = await status_response.text()
                                try:
                                    final_response_json = json.loads(status_body)
                                    final_response_text = None
                                except json.JSONDecodeError:
                                    final_response_json = None
                                    final_response_text = status_body

                            current_status = (
                                final_response_json.get("status")
                                if isinstance(final_response_json, dict)
                                else None
                            )
                            logger.info(
                                f"Polled job status: {current_status or 'unknown'}",
                                extra={"request_id": request_id, "job_id": job_id},
                            )
                            if current_status not in RUNPOD_PENDING_STATUSES:
                                break

                    logger.info(f"Submit response: {final_status_code}", extra={"request_id": request_id, "status_code": final_status_code})
                    return build_submit_result(
                        status_code=final_status_code,
                        content_type=final_content_type,
                        endpoint_url=request.endpoint_url,
                        response_json=final_response_json,
                        response_text=final_response_text,
                    )
    except asyncio.TimeoutError as exc:
        logger.error(f"Submit request timed out", extra={"request_id": request_id})
        raise HTTPException(status_code=504, detail="Submit request timed out.") from exc
    except aiohttp.ClientError as exc:
        logger.error(f"Submit request failed: {exc}", extra={"request_id": request_id})
        raise HTTPException(status_code=502, detail=f"Submit request failed: {exc}") from exc

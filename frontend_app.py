from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.requests import Request
from starlette.responses import Response

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

app = FastAPI(title="FLUX.1-dev Image Generator")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.middleware("http")
async def disable_frontend_caching(request: Request, call_next) -> Response:
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




@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")




@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def config() -> dict[str, object]:
    return {
        "width": {"min": 512, "max": 2048, "default": 1024, "step": 64},
        "height": {"min": 512, "max": 2048, "default": 1024, "step": 64},
        "num_inference_steps": {"min": 10, "max": 100, "default": 50},
        "guidance_scale": {"min": 1.0, "max": 10.0, "default": 3.5, "step": 0.5},
        "aspect_ratios": ASPECT_RATIOS,
    }


@app.post("/api/payload")
async def create_payload(request: PayloadRequest) -> dict[str, object]:
    # Apply aspect ratio if specified
    if request.aspect_ratio in ASPECT_RATIOS:
        dimensions = ASPECT_RATIOS[request.aspect_ratio]
        width = dimensions["width"]
        height = dimensions["height"]
    else:
        width = request.width
        height = request.height
    
    payload = {
        "prompt": request.prompt,
        "width": width,
        "height": height,
        "num_inference_steps": request.num_inference_steps,
        "guidance_scale": request.guidance_scale,
        "seed": request.seed if request.seed > 0 else None,
    }

    return {
        "payload": payload,
        "summary": {
            "width": width,
            "height": height,
            "aspect_ratio": request.aspect_ratio,
            "num_inference_steps": request.num_inference_steps,
            "guidance_scale": request.guidance_scale,
            "seed": request.seed,
        },
    }


@app.post("/api/submit")
async def submit_payload(request: SubmitRequest) -> dict[str, object]:
    headers = {"Content-Type": "application/json"}
    auth_token = request.auth_token.strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    timeout = aiohttp.ClientTimeout(total=request.timeout_seconds)

    try:
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

                return {
                    "ok": 200 <= response.status < 300,
                    "status_code": response.status,
                    "content_type": content_type or "application/octet-stream",
                    "endpoint_url": request.endpoint_url,
                    "response_json": response_json,
                    "response_text": None if response_json is not None else raw_body,
                }
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Submit request timed out.") from exc
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=f"Submit request failed: {exc}") from exc



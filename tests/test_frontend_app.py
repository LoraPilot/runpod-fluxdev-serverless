import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import frontend_app


class FakeResponse:
    def __init__(self, *, status: int, json_data=None, text_data: str | None = None, headers=None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.headers = headers or {"Content-Type": "application/json"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        if self._text_data is not None:
            return self._text_data
        return json.dumps(self._json_data or {})


class FakeClientSession:
    def __init__(self, *, post_responses=None, get_responses=None, **kwargs):
        self._post_responses = list(post_responses or [])
        self._get_responses = list(get_responses or [])
        self.post_calls = []
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, headers=None):
        self.post_calls.append({"url": url, "json": json, "headers": headers})
        return self._post_responses.pop(0)

    def get(self, url, headers=None):
        self.get_calls.append({"url": url, "headers": headers})
        return self._get_responses.pop(0)


class TestFrontendApp(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(frontend_app.app)

    def test_create_payload_wraps_input_and_requests_image_data_url(self):
        response = self.client.post(
            "/api/payload",
            json={
                "prompt": "A fox in a neon alley",
                "aspect_ratio": "4:3",
                "num_inference_steps": 35,
                "guidance_scale": 3.5,
                "seed": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["payload"]
        self.assertEqual(
            payload,
            {
                "input": {
                    "prompt": "A fox in a neon alley",
                    "width": 1152,
                    "height": 896,
                    "num_inference_steps": 35,
                    "guidance_scale": 3.5,
                    "include_image_data_url": True,
                }
            },
        )
        self.assertIsNone(response.json()["summary"]["seed"])

    def test_submit_polls_runpod_status_until_completed(self):
        fake_session = FakeClientSession(
            post_responses=[
                FakeResponse(
                    status=200,
                    json_data={"id": "job-123", "status": "IN_PROGRESS"},
                )
            ],
            get_responses=[
                FakeResponse(
                    status=200,
                    json_data={
                        "id": "job-123",
                        "status": "COMPLETED",
                        "output": {
                            "status": "success",
                            "image": "base64string",
                            "metadata": {"seed": 123},
                        },
                    },
                )
            ],
        )

        with patch("frontend_app.aiohttp.ClientSession", return_value=fake_session), \
             patch("frontend_app.asyncio.sleep", new=AsyncMock()):
            response = self.client.post(
                "/api/submit",
                json={
                    "endpoint_url": "https://api.runpod.ai/v2/test-endpoint/runsync",
                    "auth_token": "secret",
                    "payload": {"input": {"prompt": "hello"}},
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["job_status"], "COMPLETED")
        self.assertEqual(body["image_base64"], "base64string")
        self.assertEqual(body["image_data_url"], "data:image/png;base64,base64string")
        self.assertEqual(body["metadata"], {"seed": 123})
        self.assertEqual(fake_session.post_calls[0]["json"], {"input": {"prompt": "hello"}})
        self.assertEqual(
            fake_session.get_calls[0]["url"],
            "https://api.runpod.ai/v2/test-endpoint/status/job-123",
        )


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import frontend_app


class FakeResponse:
    def __init__(self, *, status: int, json_data=None, text_data: str | None = None):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        if self._text_data is not None:
            return self._text_data
        return json.dumps(self._json_data or {})

    async def json(self):
        if self._json_data is not None:
            return self._json_data
        if self._text_data is not None:
            return json.loads(self._text_data)
        return {}


class FakeClientSession:
    def __init__(self, *, post_response=None, get_response=None, **kwargs):
        self._post_response = post_response
        self._get_response = get_response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json):
        return self._post_response

    def get(self, url):
        return self._get_response


class TestFrontendApp(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(frontend_app.app)


if __name__ == "__main__":
    unittest.main()

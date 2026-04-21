import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add parent directory to path to import handler.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import handler


class TestFluxHandler(unittest.TestCase):
    """Test cases for FLUX.1-dev handler functions."""

    def test_validate_generation_params_valid(self):
        """Test validation with valid parameters."""
        params = {
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        is_valid, error_msg = handler.validate_generation_params(params)
        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)

    def test_validate_generation_params_invalid_width(self):
        """Test validation with invalid width."""
        params = {
            "width": 100,  # Below minimum
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        is_valid, error_msg = handler.validate_generation_params(params)
        self.assertFalse(is_valid)
        self.assertIn("width", error_msg)

    def test_validate_generation_params_invalid_height(self):
        """Test validation with invalid height."""
        params = {
            "width": 1024,
            "height": 3000,  # Above maximum
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        is_valid, error_msg = handler.validate_generation_params(params)
        self.assertFalse(is_valid)
        self.assertIn("height", error_msg)

    def test_validate_generation_params_invalid_steps(self):
        """Test validation with invalid inference steps."""
        params = {
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 5,  # Below minimum
            "guidance_scale": 3.5,
        }
        is_valid, error_msg = handler.validate_generation_params(params)
        self.assertFalse(is_valid)
        self.assertIn("num_inference_steps", error_msg)

    def test_validate_generation_params_invalid_guidance(self):
        """Test validation with invalid guidance scale."""
        params = {
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 15.0,  # Above maximum
        }
        is_valid, error_msg = handler.validate_generation_params(params)
        self.assertFalse(is_valid)
        self.assertIn("guidance_scale", error_msg)

    def test_build_cache_key_consistency(self):
        """Test that cache key is consistent for same parameters."""
        params1 = {
            "prompt": "test prompt",
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        params2 = {
            "prompt": "test prompt",
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        key1 = handler.build_cache_key(**params1)
        key2 = handler.build_cache_key(**params2)
        self.assertEqual(key1, key2)

    def test_build_cache_key_uniqueness(self):
        """Test that cache key differs for different parameters."""
        params1 = {
            "prompt": "test prompt",
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        params2 = {
            "prompt": "different prompt",
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 3.5,
        }
        key1 = handler.build_cache_key(**params1)
        key2 = handler.build_cache_key(**params2)
        self.assertNotEqual(key1, key2)

    def test_decode_cached_response_valid(self):
        """Test decoding a valid cached response."""
        response = {
            "status": "success",
            "image": "base64string",
            "metadata": {},
        }
        raw_value = json.dumps(response)
        decoded = handler.decode_cached_response(raw_value)
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded["cached"])
        self.assertEqual(decoded["status"], "success")

    def test_decode_cached_response_invalid_json(self):
        """Test decoding invalid JSON."""
        decoded = handler.decode_cached_response("invalid json")
        self.assertIsNone(decoded)

    def test_decode_cached_response_not_success(self):
        """Test decoding a non-success response."""
        response = {"status": "error", "error": "test error"}
        raw_value = json.dumps(response)
        decoded = handler.decode_cached_response(raw_value)
        self.assertIsNone(decoded)

    def test_handler_config_from_env(self):
        """Test configuration loading from environment variables."""
        test_env = {
            "REDIS_URL": "redis://test:6379",
            "CACHE_TTL_SECONDS": "3600",
            "FLUX_MODEL_PATH": "/test/path/model.safetensors",
        }
        with patch.dict(os.environ, test_env, clear=True):
            config = handler.HandlerConfig.from_env()
            self.assertEqual(config.redis_url, "redis://test:6379")
            self.assertEqual(config.cache_ttl_seconds, 3600)
            self.assertEqual(config.model_path, "/test/path/model.safetensors")

    @patch("handler.redis.from_url")
    def test_redis_connection_success(self, mock_redis):
        """Test successful Redis connection."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client
        
        test_env = {"REDIS_URL": "redis://localhost:6379"}
        with patch.dict(os.environ, test_env, clear=True):
            handler.config = handler.HandlerConfig.from_env()
            # Re-import to trigger connection
            import importlib
            importlib.reload(handler)
            self.assertIsNotNone(handler.redis_client)

    @patch("handler.redis.from_url")
    def test_redis_connection_failure(self, mock_redis):
        """Test Redis connection failure."""
        mock_redis.side_effect = Exception("Connection failed")
        
        test_env = {"REDIS_URL": "redis://localhost:6379"}
        with patch.dict(os.environ, test_env, clear=True):
            handler.config = handler.HandlerConfig.from_env()
            # Re-import to trigger connection
            import importlib
            importlib.reload(handler)
            # Should handle gracefully and set redis_client to None
            self.assertIsNone(handler.redis_client)


if __name__ == "__main__":
    unittest.main()

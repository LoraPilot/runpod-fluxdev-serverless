import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json
import tempfile
from pathlib import Path

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

    def test_decode_cached_response_with_image_data_url(self):
        """Test decoding a valid cached response with an opt-in image data URL."""
        response = {
            "status": "success",
            "image": "base64string",
            "metadata": {},
        }
        raw_value = json.dumps(response)
        decoded = handler.decode_cached_response(raw_value, include_image_data_url=True)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["image_data_url"], "data:image/png;base64,base64string")

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

    def test_is_diffusers_model_dir_requires_metadata(self):
        """Test local model detection requires diffusers metadata files."""
        with tempfile.TemporaryDirectory() as model_dir:
            self.assertFalse(handler.is_diffusers_model_dir(model_dir))
            Path(model_dir, "model_index.json").write_text("{}", encoding="utf-8")
            self.assertTrue(handler.is_diffusers_model_dir(model_dir))

    def test_resolve_model_path_falls_back_to_baked_image_model(self):
        """Test local resolution prefers a valid baked image model over an empty workspace directory."""
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as image_dir:
            Path(image_dir, "model_index.json").write_text("{}", encoding="utf-8")

            with patch.object(handler, "WORKSPACE_MODEL_PATH", workspace_dir), \
                 patch.object(handler, "IMAGE_MODEL_PATH", image_dir), \
                 patch.object(handler.config, "model_path", ""):
                resolved = handler.resolve_model_path(MagicMock())

            self.assertEqual(resolved, image_dir)

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

    @patch("handler.random.randint", return_value=1234)
    @patch("handler.torch.Generator")
    @patch("handler.image_to_base64", return_value="base64string")
    @patch("handler.get_flux_pipeline")
    def test_handler_allows_null_seed_and_opt_in_image_data_url(
        self,
        mock_get_flux_pipeline,
        mock_image_to_base64,
        mock_generator_cls,
        mock_randint,
    ):
        """Test that null seed falls back to random and image_data_url is opt-in."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value.images = [MagicMock()]
        mock_get_flux_pipeline.return_value = mock_pipeline

        mock_generator = MagicMock()
        mock_generator.manual_seed.return_value = "seeded-generator"
        mock_generator_cls.return_value = mock_generator

        with patch.object(handler, "redis_client", None):
            response = handler.handler({
                "id": "job-123",
                "input": {
                    "prompt": "test prompt",
                    "seed": None,
                    "include_image_data_url": True,
                },
            })

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["image"], "base64string")
        self.assertEqual(response["image_data_url"], "data:image/png;base64,base64string")
        self.assertEqual(response["metadata"]["seed"], 1234)
        mock_randint.assert_called_once()
        mock_generator.manual_seed.assert_called_once_with(1234)

    def test_handler_rejects_non_boolean_include_image_data_url(self):
        """Test validation for include_image_data_url type."""
        response = handler.handler({
            "id": "job-123",
            "input": {
                "prompt": "test prompt",
                "include_image_data_url": "yes",
            },
        })

        self.assertEqual(response["status"], "error")
        self.assertIn("include_image_data_url", response["error"])


if __name__ == "__main__":
    unittest.main()

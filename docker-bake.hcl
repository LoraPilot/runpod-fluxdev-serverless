variable "DOCKERHUB_REPO" {
  default = "runpod"
}

variable "DOCKERHUB_IMG" {
  default = "flux-dev-worker"
}

variable "RELEASE_VERSION" {
  default = "latest"
}

# Global defaults for standard CUDA 12.8.1 images
variable "BASE_IMAGE" {
  default = "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04"
}

variable "ENABLE_PYTORCH_UPGRADE" {
  default = "true"
}

variable "PYTORCH_INDEX_URL" {
  default = "https://download.pytorch.org/whl/cu128"
}

variable "PYTORCH_PACKAGES" {
  default = "torch torchvision torchaudio"
}

variable "EXTRA_PYTHON_PACKAGES" {
  default = ""
}

variable "EXTRA_PYTHON_INDEX_URL" {
  default = ""
}

variable "FLUX_DEV_PRELOAD" {
  default = ""
}

variable "HUGGINGFACE_ACCESS_TOKEN" {
  default = ""
}

group "default" {
  targets = ["base", "base-cuda12-8-1", "base-cuda13-0", "flux-dev", "flux-dev-cuda13"]
}

target "base" {
  context = "."
  dockerfile = "Dockerfile"
  target = "base"
  platforms = ["linux/amd64"]
  args = {
    BASE_IMAGE = "${BASE_IMAGE}"
    ENABLE_PYTORCH_UPGRADE = "${ENABLE_PYTORCH_UPGRADE}"
    PYTORCH_INDEX_URL = "${PYTORCH_INDEX_URL}"
    PYTORCH_PACKAGES = "${PYTORCH_PACKAGES}"
    EXTRA_PYTHON_PACKAGES = "${EXTRA_PYTHON_PACKAGES}"
    EXTRA_PYTHON_INDEX_URL = "${EXTRA_PYTHON_INDEX_URL}"
        FLUX_DEV_PRELOAD = "${FLUX_DEV_PRELOAD}"
  }
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-base"]
}

target "base-cuda12-8-1" {
  context = "."
  dockerfile = "Dockerfile"
  target = "base"
  platforms = ["linux/amd64"]
  args = {
    BASE_IMAGE = "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04"
    ENABLE_PYTORCH_UPGRADE = "true"
    PYTORCH_INDEX_URL = "https://download.pytorch.org/whl/cu128"
    PYTORCH_PACKAGES = "${PYTORCH_PACKAGES}"
    EXTRA_PYTHON_PACKAGES = "${EXTRA_PYTHON_PACKAGES}"
    EXTRA_PYTHON_INDEX_URL = "${EXTRA_PYTHON_INDEX_URL}"
        FLUX_DEV_PRELOAD = "${FLUX_DEV_PRELOAD}"
  }
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-base-cuda12.8.1"]
}

target "base-cuda13-0" {
  context = "."
  dockerfile = "Dockerfile"
  target = "base"
  platforms = ["linux/amd64"]
  args = {
    BASE_IMAGE = "nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04"
    ENABLE_PYTORCH_UPGRADE = "true"
    PYTORCH_INDEX_URL = "https://download.pytorch.org/whl/cu130"
    PYTORCH_PACKAGES = "${PYTORCH_PACKAGES}"
    EXTRA_PYTHON_PACKAGES = "${EXTRA_PYTHON_PACKAGES}"
    EXTRA_PYTHON_INDEX_URL = "${EXTRA_PYTHON_INDEX_URL}"
        FLUX_DEV_PRELOAD = "${FLUX_DEV_PRELOAD}"
  }
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-base-cuda13.0"]
}

target "flux-dev" {
  context = "."
  dockerfile = "Dockerfile"
  target = "base"
  platforms = ["linux/amd64"]
  args = {
    BASE_IMAGE = "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04"
    ENABLE_PYTORCH_UPGRADE = "true"
    PYTORCH_INDEX_URL = "https://download.pytorch.org/whl/cu128"
    PYTORCH_PACKAGES = "${PYTORCH_PACKAGES}"
    EXTRA_PYTHON_PACKAGES = "${EXTRA_PYTHON_PACKAGES}"
    EXTRA_PYTHON_INDEX_URL = "${EXTRA_PYTHON_INDEX_URL}"
    FLUX_DEV_PRELOAD = "true"
    HUGGINGFACE_ACCESS_TOKEN = "${HUGGINGFACE_ACCESS_TOKEN}"
  }
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-flux-dev-cu128"]
}

target "flux-dev-cuda13" {
  context = "."
  dockerfile = "Dockerfile"
  target = "base"
  platforms = ["linux/amd64"]
  args = {
    BASE_IMAGE = "nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04"
    ENABLE_PYTORCH_UPGRADE = "true"
    PYTORCH_INDEX_URL = "https://download.pytorch.org/whl/cu130"
    PYTORCH_PACKAGES = "${PYTORCH_PACKAGES}"
    EXTRA_PYTHON_PACKAGES = "${EXTRA_PYTHON_PACKAGES}"
    EXTRA_PYTHON_INDEX_URL = "${EXTRA_PYTHON_INDEX_URL}"
    FLUX_DEV_PRELOAD = "true"
    HUGGINGFACE_ACCESS_TOKEN = "${HUGGINGFACE_ACCESS_TOKEN}"
  }
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-flux-dev-cu130"]
}

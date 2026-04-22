# Customization

This guide covers methods for customizing your FLUX.1-dev worker deployment.

> [!TIP]
>
> **The FLUX.1-dev model is already included in the Docker image.**
>
> You only need customization if you want to add additional models, LoRAs, or modify the environment.

---

There are two primary methods for customization:

1.  **Custom Dockerfile (recommended):** Create your own `Dockerfile` starting from the base image to bake additional models or dependencies directly into your image.
2.  **Network Volume:** Store additional models on a persistent network volume attached to your RunPod endpoint.

## Method 1: Custom Dockerfile

> [!NOTE]
>
> This method does NOT require forking the repository.

This is the most flexible approach for creating reproducible, customized worker environments.

1.  **Create a `Dockerfile`:** In your own project directory, create a file named `Dockerfile`.
2.  **Start with a Base Image:** Begin your `Dockerfile` by referencing the official base image.
    ```Dockerfile
    # start from a clean base image (replace <version> with the desired release)
    FROM your-dockerhub-id/flux-dev-worker:<version>-base-cuda12.8.1
    ```
3.  **Add Additional Models:** Use `wget` or `curl` to download additional models and place them in the correct directories.
    ```Dockerfile
    # Download additional LoRAs or models
    RUN wget -O /workspace/models/loras/custom_lora.safetensors https://huggingface.co/...
    ```

Once you have created your custom `Dockerfile`, refer to the [Deployment Guide](deployment.md#deploying-custom-setups) for instructions on how to build, push and deploy your custom image to RunPod.

### Complete Custom `Dockerfile` Example

```Dockerfile
# start from a clean base image (replace <version> with the desired release)
FROM your-dockerhub-id/flux-dev-worker:latest-base-cuda12.8.1

# download additional models using wget or curl
RUN wget -O /workspace/models/loras/custom_lora.safetensors https://huggingface.co/...
```

## Method 2: Network Volume

Using a Network Volume is primarily useful if you want to manage **models** separately from your worker image, especially if they are large or change often.

1.  **Create a Network Volume**:
    - Follow the [RunPod Network Volumes guide](https://docs.runpod.io/pods/storage/create-network-volumes) to create a volume in the same region as your endpoint.
2.  **Populate the Volume with Models**:
    - Use one of the methods described in the RunPod guide (e.g., temporary Pod + `wget`, direct upload, or the S3-compatible API) to place your model files into the correct directory structure **within the volume**.
    - For **serverless endpoints**, the network volume is mounted at `/runpod-volume`, and models should be placed under `/runpod-volume/models/...`. See [Network Volumes & Model Paths](network-volumes.md) for the exact structure and debugging tips.
      ```bash
      # Example structure inside the Network Volume (serverless worker view):
      # /runpod-volume/models/checkpoints/your_model.safetensors
      # /runpod-volume/models/loras/your_lora.pt
      # /runpod-volume/models/vae/your_vae.safetensors
      ```
    - **Important:** Ensure models are placed in the correct subdirectories (e.g., checkpoints in `models/checkpoints`, LoRAs in `models/loras`). If models are not detected, enable `NETWORK_VOLUME_DEBUG` as described in [Network Volumes & Model Paths](network-volumes.md).
3.  **Configure Your Endpoint**:
    - Use the Network Volume in your endpoint configuration:
      - Either create a new endpoint or update an existing one (see [Deployment Guide](deployment.md)).
      - In the endpoint configuration, under `Advanced > Select Network Volume`, select your Network Volume.

> [!NOTE]
>
> - When a Network Volume is correctly attached, the worker will automatically detect and load models from the standard directories (`/runpod-volume/models/...`). For directory mapping details and troubleshooting, see [Network Volumes & Model Paths](network-volumes.md).
> - This method is **not suitable for installing custom nodes**; use the Custom Dockerfile method for that.

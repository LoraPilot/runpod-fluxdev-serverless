# Customization

This guide covers methods for adding your own models, custom nodes, and static input files into a custom image derived from this worker.

> [!TIP]
>
> **Looking for the easiest way to deploy custom workflows?**
>
>
> Use the manual methods below only if you need fine-grained control or prefer to manage everything yourself.

---

There are two primary methods for **manual** customization:

1.  **Custom Dockerfile (recommended for manual setup):** Create your own `Dockerfile` starting `FROM` one of this repository's base images. This allows you to bake specific models and dependencies directly into your image. **This method does not require forking the repository.**
2.  **Network Volume:** Store models on a persistent network volume attached to your RunPod endpoint. This is useful if you frequently change models or have very large models you don't want to include in the image build process.

## Method 1: Custom Dockerfile

> [!NOTE]
>
> This method does NOT require forking the repository.

This is the most flexible and recommended approach for creating reproducible, customized worker environments.

1.  **Create a `Dockerfile`:** In your own project directory, create a file named `Dockerfile`.
2.  **Start with a Base Image:** Begin your `Dockerfile` by referencing one of the official base images. Using the `-base` tag is recommended as it provides a clean Python environment without pre-packaged models.
    ```Dockerfile
    # start from a clean base image (replace <version> with the desired release)
    FROM your-dockerhub-id/flux-dev-worker:<version>-base-cuda12.8.1
    ```
3.  **Install Custom Nodes:** Use the `comfy-node-install` (we had introduce our own cli tool here, as there is a [problem with comfy-cli not showing errors during installation](https://github.com/Comfy-Org/comfy-cli/pull/275)) command to add custom nodes by their name or URL, see [Comfy Registry](https://registry.comfy.org) to find the correct name. You can list multiple nodes.
    ```Dockerfile
    ```
4.  **Download Models:** Use `wget` or `curl` to download models and place them in the correct directories.
>
> checkpoints, clip, clip_vision, configs, controlnet, diffusers, embeddings, gligen, hypernetworks, loras, style_models, unet, upscale_models, vae, vae_approx, animatediff_models, animatediff_motion_lora, ipadapter, photomaker, sams, insightface, facerestore_models, facedetection, mmdets, instantid

5.  **Add Static Input Files (Optional):** If your workflows consistently require specific input images, masks, videos, etc., you can copy them directly into the image.

- Create an `input/` directory in the same folder as your `Dockerfile`.
- Place your static files inside this `input/` directory.
- Add a `COPY` command to your `Dockerfile`:

  ```Dockerfile
  # Copy local static input files into the ComfyUI input directory
  COPY input/ /comfyui/input/
  ```

- These files can then be referenced in your workflow using a "Load Image" (or similar) node pointing to the filename (e.g.,`my_static_image.png`).

Once you have created your custom `Dockerfile`, refer to the [Deployment Guide](deployment.md#deploying-custom-setups) for instructions on how to build, push and deploy your custom image to RunPod.

### Complete Custom `Dockerfile` Example

```Dockerfile
# start from a clean base image (replace <version> with the desired release)
FROM your-dockerhub-id/flux-dev-worker:latest-base-cuda12.8.1

# install custom nodes using comfy-cli
RUN comfy-node-install comfyui-kjnodes comfyui-ic-light comfyui_ipadapter_plus comfyui_essentials ComfyUI-Hangover-Nodes

# download models --url https://huggingface.co/KamCastle/jugg/resolve/main/juggernaut_reborn.safetensors --relative-path models/checkpoints --filename juggernaut_reborn.safetensors
RUN comfy model download --url https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.bin --relative-path models/ipadapter --filename ip-adapter-plus_sd15.bin
RUN comfy model download --url https://huggingface.co/shiertier/clip_vision/resolve/main/SD15/model.safetensors --relative-path models/clip_vision --filename models.safetensors
RUN comfy model download --url https://huggingface.co/lllyasviel/ic-light/resolve/main/iclight_sd15_fcon.safetensors --relative-path models/diffusion_models --filename iclight_sd15_fcon.safetensors

# Copy local static input files into the ComfyUI input directory (delete if not needed)
# Assumes you have an 'input' folder next to your Dockerfile
COPY input/ /comfyui/input/
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

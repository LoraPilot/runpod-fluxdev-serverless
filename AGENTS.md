<!-- Do not edit or remove this section -->
<!-- This document exists for non-obvious, error-prone shortcomings in the codebase, the model, or the tooling that an agent cannot figure out by reading the code alone. No architecture overviews, file trees, build commands, or standard behavior. When you encounter something that belongs here, first consider whether a code change could eliminate it and suggest that to the user. Only document it here if it can't be reasonably fixed. -->

---

## Non-obvious constraints

- **No hot-reload**: handler.py and start.sh are `ADD`ed into the Docker image at build time (to `/`). Any change requires a full `docker build` before testing with docker-compose.
- **Platform mismatch**: Always build with `--platform linux/amd64` for Runpod deployment. Omitting this on ARM hosts (Apple Silicon) produces images that silently fail on Runpod.
- **No linter or formatter configured**: Follow PEP 8 by convention; there are no pre-commit hooks or CI lint checks.
- **Network volume mount point**: Models on a network volume should be placed in `/workspace/models/` structure as defined in bootstrap_flux.sh. The volume is expected at `/runpod-volume`.

- **General pattern**: When a custom node fails with import errors, check its dependency chain and pin versions in the Dockerfile with `uv pip install`.

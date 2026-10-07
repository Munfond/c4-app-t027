#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
carla_root=${CARLA_ROOT:-"${project_root}/data/runtime/carla-0.9.16"}

if [[ ! -x ${carla_root}/CarlaUE4.sh ]]; then
  echo "CARLA server not installed at ${carla_root}; set CARLA_ROOT if installed elsewhere." >&2
  exit 1
fi
if ! command -v nvidia-smi >/dev/null || ! nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA driver is not ready. Install system prerequisites and reboot first." >&2
  exit 1
fi
if [[ $(id -u) -eq 0 ]]; then
  echo "Run the CARLA server as your normal user, not root." >&2
  exit 1
fi

# Hybrid laptop: select NVIDIA via PRIME. Keep rendering for RGB/semantic sensors;
# no_rendering_mode would make GPU sensor images empty.
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export __VK_LAYER_NV_optimus=NVIDIA_only
cd -- "${carla_root}"
exec ./CarlaUE4.sh -RenderOffScreen -quality-level=Low \
  -carla-rpc-port=2000 -nosound "$@"

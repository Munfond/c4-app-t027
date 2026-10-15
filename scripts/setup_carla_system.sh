#!/usr/bin/env bash
# Ubuntu desktop prerequisites; run manually with sudo in your own terminal.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run: sudo bash $0" >&2
  exit 1
fi
. /etc/os-release
if [[ ${ID} != ubuntu || ${VERSION_ID} != 22.04 ]]; then
  echo "This installer was reviewed for Ubuntu 22.04 only." >&2
  exit 1
fi

apt-get -o Acquire::ForceIPv4=true -o Acquire::http::Timeout=15 \
  -o Acquire::https::Timeout=15 -o Acquire::Retries=1 update
apt-get install -y libvulkan1 vulkan-tools libomp5 libjpeg-turbo8 \
  libpng16-16 libtiff5 libx11-6 libxcursor1 libxrandr2 libxi6 libglib2.0-0
# Ubuntu chooses the recommended driver for the detected card. No kernel upgrade,
# .run installer, graphics-session restart, or automatic machine reboot here.
ubuntu-drivers install
echo "System packages installed. Save your work, then reboot to activate NVIDIA."

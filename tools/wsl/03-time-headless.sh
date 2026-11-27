#!/usr/bin/env bash
# Record whether a Linux headless timing is possible. Does not launch anything.
# Does not call headless.py (it is hard-wired to the Windows boot.exe).
set -euo pipefail
source "$(dirname "$0")/env.sh"

if [[ "${FE_WSL_GPU_OK:-0}" != "1" ]]; then
  echo "refusing: set FE_WSL_GPU_OK=1 only when no Windows capture is running"
  exit 2
fi
mkdir -p "${LOG}"

real_gpu=0
if python3 "$(dirname "$0")/vkprobe.py" > "${LOG}/vkprobe.txt" 2>&1; then
  real_gpu=1
fi

BOOT=""
cand="${SCRATCH}/cargo-target/zakuro-boot/release/examples/boot"
if [[ -x "${cand}" && ! -d "${cand}" ]]; then
  BOOT="${cand}"
fi

{
  cat "${LOG}/vkprobe.txt"
  echo "vulkan_real_device ${real_gpu}"
  echo "windows_boot_exe: not run (${REPO}/engine/target/zakuro-test/release/examples/boot.exe)"
  if [[ -n "${BOOT}" ]]; then
    echo "linux_boot ${BOOT}"
    file "${BOOT}" || true
  else
    echo "linux_boot none (expected at cargo-target/zakuro-boot/release/examples/boot after 02)"
  fi
  echo "headless.py launches boot.exe only. No Linux timing until that path is a flag."
  echo "save-load without a real Vulkan device is blocked by inference from risk 20, not by a WSL run."
  echo "headless: not started"
} | tee "${LOG}/headless.txt"

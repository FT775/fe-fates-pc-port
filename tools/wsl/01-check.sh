#!/usr/bin/env bash
# Environment check. Creates $HOME/<game key>-wsl-scratch/logs. Does not build or run.
# Not read-only: the mkdir is intentional. Downloads nothing.
set -euo pipefail
source "$(dirname "$0")/env.sh"

echo "repo: ${REPO}"
if [[ ! -d "${REPO}" ]]; then
  echo "repo: NOT VISIBLE"
  exit 1
fi
echo "repo: visible"
echo "note: /mnt/d is drvfs. Cargo for this trial must use ${SCRATCH} (ext4), not the repo tree."

mkdir -p "${LOG}"
echo "scratch: ${SCRATCH} (mkdir done; this script is not read-only)"
echo "RUSTUP_HOME=${RUSTUP_HOME} CARGO_HOME=${CARGO_HOME} (both inside the scratch)"
df -h "${HOME}" | sed -n '1,2p'
echo "cpus: $(nproc)  mem: $(free -g | awk '/^Mem:/{print $2" GiB"}')"

need=(python3 cargo rustc gcc pkg-config file git)
missing=0
if [[ ! -x /usr/bin/time ]]; then
  echo "tool /usr/bin/time: missing"
  missing=1
else
  echo "tool /usr/bin/time: present"
fi
for cmd in "${need[@]}"; do
  if command -v "${cmd}" >/dev/null 2>&1; then
    echo "tool ${cmd}: $(command -v "${cmd}")"
  else
    echo "tool ${cmd}: missing"
    missing=1
  fi
done

pyver="$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo missing)"
echo "python3: ${pyver} (need >= 3.11)"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || missing=1

if command -v rustup >/dev/null 2>&1; then
  echo "rustup: $(rustup --version 2>/dev/null | head -1)"
  if rustup toolchain list 2>/dev/null | grep -q '^stable'; then
    echo "rustup stable: present ($(rustc +stable --version 2>/dev/null || echo unreadable))"
  else
    echo "rustup stable: missing (install it; RUSTUP_AUTO_INSTALL is 0)"
    missing=1
  fi
else
  echo "rustup: missing. Install into the scratch (README 'Install'), then rerun."
  missing=1
fi

echo "pins:"
for name in zakuro 3dsrecomp; do
  dir="${REPO}/engine/${name}"
  pin="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["repos"][sys.argv[2]]["commit"])' "${REPO}/config/upstream.json" "${name}")"
  echo "  pin ${name}: ${pin}"
  if ! head="$(git -C "${dir}" rev-parse HEAD 2>&1)"; then
    echo "  checkout ${name}: git could not read ${dir}: ${head}"
    echo "  if the error is safe.directory, add that path and rerun. This script does not change git config."
    missing=1
    continue
  fi
  echo "  checkout ${name}: ${head}"
  if [[ "${name}" == "3dsrecomp" ]]; then
    if [[ "${head}" == "${pin}" ]]; then
      echo "  3dsrecomp: HEAD equals pin"
    else
      echo "  3dsrecomp: HEAD is not the pin"
      missing=1
    fi
  else
    if git -C "${dir}" merge-base --is-ancestor "${pin}" HEAD; then
      echo "  zakuro: pin is an ancestor of HEAD (the port branch may be ahead of the pin)"
    else
      echo "  zakuro: pin is not an ancestor of HEAD"
      missing=1
    fi
  fi
done

# Vulkan: vulkaninfo if present, otherwise vkprobe.py (ctypes on libvulkan.so.1). Per device;
# a CPU device (llvmpipe/lavapipe) never counts. Informational: builds do not need a GPU.
if command -v vulkaninfo >/dev/null 2>&1; then
  vulkaninfo --summary > "${LOG}/vulkaninfo.txt" 2>&1 || true
fi
if python3 "$(dirname "$0")/vkprobe.py" 2>&1 | tee "${LOG}/vkprobe.txt"; then
  echo "vulkan: real device present"
else
  echo "vulkan: no real (non-CPU) device; headless game runs stay off in WSL"
fi

echo "FE_WSL_GPU_OK=${FE_WSL_GPU_OK:-unset}"
if [[ "${missing}" -ne 0 ]]; then
  echo "check: FAIL"
  exit 1
fi
echo "check: done"

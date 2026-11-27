#!/usr/bin/env bash
# Install rustup + the stable toolchain (minimal profile) INSIDE the scratch. No sudo.
# Downloads: rustup-init from sh.rustup.rs and the toolchain from static.rust-lang.org. Nothing else.
# Does not edit ~/.profile or ~/.bashrc (--no-modify-path); env.sh puts the scratch cargo on PATH.
set -euo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p "${SCRATCH}" "${LOG}"
if command -v rustup >/dev/null 2>&1 && rustup toolchain list | grep -q '^stable'; then
  echo "rust: already in the scratch ($(rustc +stable --version))"
  exit 0
fi
init="${SCRATCH}/rustup-init.sh"
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o "${init}"
sh "${init}" -y --no-modify-path --profile minimal --default-toolchain stable 2>&1 | tail -5
rm -f "${init}"
echo "rust: $(rustc +stable --version)"

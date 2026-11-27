#!/usr/bin/env bash
# Time direct cargo builds in an ext4 scratch copy. Never calls engine.py, never writes engine/.
# Refuses unless the operator has confirmed no Windows capture is running.
#
# Network: crates.io only (cargo fetch, timed apart from the compile). The two git dependencies
# (github.com/fearkov/zakuro and /3dsrecomp, pinned by the Cargo.lock files) are served from a
# scratch copy of the Windows cargo git cache through git's insteadOf, and GIT_ALLOW_PROTOCOL=file
# makes any other git URL fail instead of downloading. The compile steps run with --offline.
set -euo pipefail
source "$(dirname "$0")/env.sh"

if [[ "${FE_WSL_GPU_OK:-0}" != "1" ]]; then
  echo "refusing: set FE_WSL_GPU_OK=1 only when no Windows capture is running"
  exit 2
fi

if command -v tasklist.exe >/dev/null 2>&1; then
  busy=""
  for image in "boot.exe" "3dsrecomp.exe" "${PROGRAM_EXE}" "replay.exe"; do
    if tasklist.exe /FI "IMAGENAME eq ${image}" 2>/dev/null | grep -qi "${image}"; then
      busy="${busy} ${image}"
    fi
  done
  if [[ -n "${busy}" ]]; then
    echo "refusing: Windows capture or build tool is running:${busy}"
    exit 2
  fi
fi

SRC="${SCRATCH}/src"
MIRROR="${SCRATCH}/git-mirror"
BUDGET_SEC="${FE_WSL_BUDGET_SEC:-5400}"   # 90 minutes for the whole script, then stop
T0=$(date +%s)
export RUSTUP_TOOLCHAIN=stable

left() { echo $(( BUDGET_SEC - ( $(date +%s) - T0 ) )); }
mkdir -p "${LOG}"
stamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
echo "build-start $(stamp) cpus=$(nproc) $(rustc --version)" | tee "${LOG}/builds.txt"
echo "engine.py: not called" | tee -a "${LOG}/builds.txt"

# Sources: the committed HEAD of each checkout (zakuro = pin + our patches on the port branch; 3dsrecomp = pin,
# unmodified, personal, never shared). git archive copies tracked files only, no .git, no target/.
rm -rf "${SRC}"
mkdir -p "${SRC}/zakuro" "${SRC}/3dsrecomp"
for name in zakuro 3dsrecomp; do
  git -C "${REPO}/engine/${name}" archive --format=tar HEAD | tar -x -C "${SRC}/${name}"
  echo "copied ${name} at $(git -C "${REPO}/engine/${name}" rev-parse HEAD) (git archive HEAD)" | tee -a "${LOG}/builds.txt"
done

# Git dependencies from the Windows cargo cache (read only; copied, never written back).
GITDB="${FE_WSL_GITDB:-}"
if [[ -z "${GITDB}" ]]; then
  winhome="$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')"
  GITDB="$(wslpath "${winhome}")/.cargo/git/db"
fi
rm -rf "${MIRROR}"
mkdir -p "${MIRROR}"
n=0
for name in 3dsrecomp zakuro; do
  db="$(ls -d "${GITDB}/${name}-"* 2>/dev/null | head -1 || true)"
  if [[ -z "${db}" ]]; then
    echo "no ${name} in ${GITDB}; refusing to fetch it from GitHub" | tee -a "${LOG}/builds.txt"
    exit 3
  fi
  cp -r "${db}" "${MIRROR}/${name}.git"
  echo "git dep ${name}: local mirror from ${db}" | tee -a "${LOG}/builds.txt"
  export "GIT_CONFIG_KEY_${n}=url.file://${MIRROR}/${name}.git.insteadOf"
  export "GIT_CONFIG_VALUE_${n}=https://github.com/fearkov/${name}"
  n=$((n + 1))
done
export GIT_CONFIG_KEY_${n}=uploadpack.allowAnySHA1InWant GIT_CONFIG_VALUE_${n}=true; n=$((n + 1))
export GIT_CONFIG_KEY_${n}=safe.directory GIT_CONFIG_VALUE_${n}='*'; n=$((n + 1))
export GIT_CONFIG_COUNT=${n}
export GIT_ALLOW_PROTOCOL=file
export CARGO_NET_GIT_FETCH_WITH_CLI=true

timed() {   # timed <label> <cmd...>: wall seconds into builds.txt, output into <label>.log
  local name="$1"
  shift
  local budget
  budget="$(left)"
  if (( budget <= 0 )); then
    echo "${name}: SKIPPED, 90-minute budget used up" | tee -a "${LOG}/builds.txt"
    return 1
  fi
  echo "timing ${name}: $*" | tee -a "${LOG}/builds.txt"
  local rc=0
  /usr/bin/time -f "${name}_sec %e" -o "${LOG}/builds.txt" -a \
      timeout "${budget}" "$@" >"${LOG}/${name}.log" 2>&1 || rc=$?
  echo "${name}: exit ${rc}$( (( rc == 124 )) && echo ' (TIMEOUT: budget)' )" | tee -a "${LOG}/builds.txt"
  return "${rc}"
}

ZM="${SRC}/zakuro/Cargo.toml"
RM="${SRC}/3dsrecomp/Cargo.toml"
TG="${SCRATCH}/cargo-target"
rm -rf "${TG}"   # clean builds every run, so the numbers compare (the crate cache stays)
timed fetch-zakuro cargo fetch --locked --manifest-path "${ZM}" || true
timed fetch-3dsrecomp cargo fetch --locked --manifest-path "${RM}" || true
timed zakuro cargo build --release --locked --offline -p zakuro --manifest-path "${ZM}" --target-dir "${TG}/zakuro" || true
timed zakuro-boot cargo build --release --locked --offline -p zakuro-core --example boot --manifest-path "${ZM}" --target-dir "${TG}/zakuro-boot" || true
timed 3dsrecomp cargo build --release --locked --offline --manifest-path "${RM}" --target-dir "${TG}/3dsrecomp" || true

recomp="${TG}/3dsrecomp/release/3dsrecomp"
if [[ ! -x "${recomp}" || -d "${recomp}" ]]; then
  echo "no Linux 3dsrecomp; capture library not built (Windows exe not used)" | tee -a "${LOG}/builds.txt"
elif [[ -z "${FE_WSL_ROM:-}" ]]; then
  echo "FE_WSL_ROM unset; capture library not built" | tee -a "${LOG}/builds.txt"
else
  # build.py refuses any --out outside build/; harness-wsl is never build/harness/lib.
  OUT="${REPO}/build/harness-wsl"
  timed harness-build python3 "${REPO}/tools/harness/build.py" --out "${OUT}" --recomp "${recomp}" --rom "${FE_WSL_ROM}" || true
  # Same 3dsrecomp command build.py ran, same staged overrides, but the output folder on ext4:
  # separates drvfs cost from compile cost. Always with an explicit folder (never the install
  # default). The output is generated C from the ROM: deleted right after the timing.
  if [[ -d "${OUT}/overrides" ]]; then
    EXT4="${SCRATCH}/harness-ext4"
    rm -rf "${EXT4}"
    mkdir -p "${EXT4}/lib"
    timed harness-ext4 "${recomp}" build "${FE_WSL_ROM}" "${EXT4}/lib" --overrides "${OUT}/overrides" || true
    ls -l "${EXT4}/lib/"*.so >> "${LOG}/builds.txt" 2>&1 || true
    rm -rf "${EXT4}"
    echo "harness-ext4: output deleted" | tee -a "${LOG}/builds.txt"
  fi
fi

echo "build-end $(stamp)" | tee -a "${LOG}/builds.txt"
echo "logs: ${LOG}"

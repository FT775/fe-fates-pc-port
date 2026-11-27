# Sourced by 01-04. Every write of this trial goes under ${SCRATCH} (ext4, the Linux home),
# except the optional capture library, which build.py itself confines to build/harness-wsl.
# The repo these scripts live in (never another port's folder), and its game key and program
# name from config/game.json, so two ports' trials never share a scratch folder.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GAME_KEY="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["key"])' "${REPO}/config/game.json" 2>/dev/null || echo game)"
PROGRAM_EXE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["port"]["standalone_name"])' "${REPO}/config/game.json" 2>/dev/null || echo game.exe)"
SCRATCH="${HOME}/${GAME_KEY}-wsl-scratch"
LOG="${SCRATCH}/logs"
# Rust lives inside the scratch too, so deleting ${SCRATCH} removes the whole trial.
export RUSTUP_HOME="${SCRATCH}/rustup"
export CARGO_HOME="${SCRATCH}/cargo-home"
# Plain Linux PATH: WSL interop appends the Windows PATH (Windows cargo, Git-for-Windows tools).
# Only System32 is kept, for tasklist.exe and cmd.exe.
export PATH="${CARGO_HOME}/bin:/usr/local/bin:/usr/bin:/bin:/mnt/c/Windows/System32"
export RUSTUP_AUTO_INSTALL=0
# x86_64 -dev headers unpacked by 00-dev-libs.sh (no sudo), if present.
if [[ -d "${SCRATCH}/sysroot/usr/lib/x86_64-linux-gnu/pkgconfig" ]]; then
  export PKG_CONFIG_PATH="${SCRATCH}/sysroot/usr/lib/x86_64-linux-gnu/pkgconfig"
fi
if ls "${SCRATCH}"/sysroot/usr/lib/llvm-*/lib/libclang*.so* >/dev/null 2>&1; then
  export LIBCLANG_PATH="$(dirname "$(ls "${SCRATCH}"/sysroot/usr/lib/llvm-*/lib/libclang*.so* | head -1)")"
fi

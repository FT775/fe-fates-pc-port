> Fates note (2026-11-10): these scripts came from the Awakening port. `env.sh` now takes the repo
> from its own location and the scratch name and program name from `config/game.json` (`key`,
> `port.standalone_name`), and the switches are `FE_WSL_*`. The timings and disk figures below are
> Awakening's and were not re-measured for Fates. Nothing here was run in the Fates repo.

# WSL trial runbook

ELI5: This is a checklist for trying the build on Linux (WSL), to see if it is faster. It was run once on 2026-11-10 (Results at the end): Linux builds the game library about as fast as Windows, not clearly faster, and it cannot run the game tests because WSL here has no real graphics device. It must not touch the Windows build.

Status 2026-11-10: run once (Results below); the scripts were fixed during that run. Measurement only. The repo stays on D:. Scratch lives under the Linux home, on ext4, not on `/mnt/d` (drvfs is the slow path). Nothing in this folder is run by writing it.

Gate: after H4b and the H5 routes, and only when no Windows capture is running. Both heavy scripts refuse unless `FE_WSL_GPU_OK=1`.

## Do not call engine.py

`tools/engine/engine.py` always passes `--target-dir engine/target/<name>` and rewrites `engine/build-record.json`. A WSL run would write onto D: and clobber the record of the played build. It also forces `RUSTUP_TOOLCHAIN=stable-x86_64-pc-windows-msvc`. These scripts never call it. `FEF_ENGINE_DIR` (config/game.json `port.env_prefix` + `_ENGINE_DIR`) outside the repo crashes it; do not set that either.

## What gets copied

The cargo build uses a copy under `$HOME/<game key>-wsl-scratch/src`, not the D: tree.

- `engine/zakuro` is upstream plus our patches. Copy it.
- `engine/3dsrecomp` is personal, unmodified, never shared (all rights reserved, `config/upstream.json`). Copy it for the timing. Do not describe it as "upstream plus our patches." Do not commit the copy.

Do not copy the ROM, `extracted/`, `build/`, `asm/`, or generated C into the Linux home.

Pins: `01-check.sh` uses `git merge-base --is-ancestor` for Zakuro (HEAD on the port branch `fe14` (config/upstream.json), must descend from pin `c856685cc867bc6d4ac0f765844ca037ae735941`) and requires 3dsrecomp HEAD to equal `df82e6e3c1231606c38e0f2786dd07f6067979ab`. If `git` refuses the D: path, add it as `safe.directory` and rerun. This script does not change git config.

## Builds

Direct cargo, in the scratch copy (`git archive HEAD` of each checkout: tracked files only), `RUSTUP_TOOLCHAIN=stable`, `RUSTUP_AUTO_INSTALL=0`, `RUSTUP_HOME` and `CARGO_HOME` inside the scratch (`env.sh`), and a plain Linux `PATH` (WSL interop otherwise appends the Windows PATH, Windows cargo included). Target dirs are wiped at the start of every run, so the numbers are clean builds; the crate cache stays.

Downloads: `cargo fetch --locked` (crates.io only) is timed on its own; the compiles run `--offline`. The two git dependencies in the lock files (`github.com/fearkov/3dsrecomp` for Zakuro, `github.com/fearkov/zakuro` for 3dsrecomp's optional `verify`) are not fetched from GitHub. `02` copies the Windows cargo git cache (`%USERPROFILE%\.cargo\git\db`, read only) into the scratch and points git at it with `insteadOf` (env `GIT_CONFIG_*`, no config file changed) and `GIT_ALLOW_PROTOCOL=file`, so any other git URL fails instead of downloading. The whole script has a 90-minute budget (`timeout`). Separate target dirs:

- `$HOME/<game key>-wsl-scratch/cargo-target/zakuro`
- `$HOME/<game key>-wsl-scratch/cargo-target/3dsrecomp`

Commands: `cargo build --release --locked -p zakuro`, and `cargo build --release --locked -p zakuro-core --example boot`. The Linux boot, if `02` built it, is `cargo-target/zakuro-boot/release/examples/boot`.

The capture library, if attempted, is:

```
python3 tools/harness/build.py --out build/harness-wsl --recomp <linux 3dsrecomp> --rom "$FE_WSL_ROM"
```

`--out` must be `build/harness-wsl`, never `build/harness/lib`. That folder is the Windows capture library. Touching it makes `check-fresh` stale and races a Windows run. If there is no Linux `3dsrecomp`, skip the library build and record that. Do not point `--recomp` at the Windows exe.

`headless.py` is hard-wired to `engine/target/zakuro-test/release/examples/boot.exe`. `03` does not call it. A Linux timing waits on a `--boot` flag. Until then, "no Linux boot" means "do not move capture."

## Vulkan

Risk 20: the software rasterizer crashes boot.exe once a save is loaded [high that it crashes, med on the cause]. A guest with no real Vulkan device cannot do that save-load path. That "cannot" is an inference from risk 20, not a run we have done in WSL.

Reject `llvmpipe` and `lavapipe` (`deviceType` CPU). A software device is not a pass.

## How to read the result

Move capture to Linux only if all three are true:

1. The capture library build is clearly faster than the Windows 126 s already measured [high, HARNESS.md H3].
2. Two Linux save-load runs match each other on guest memory and instruction count. Compare with Windows only on the non-VRAM sections (risk 20: GPU output can differ by driver).
3. The vhdx growth is acceptable after `fstrim` and a compact, and the compact was actually done once.

Otherwise stay on the toolchain that produced the played exe.

## Scripts

Run from an Ubuntu WSL2 shell, not from cmd. cmd breaks on the parentheses in this path.

Before anyone commits these scripts, `.gitattributes` already has `*.sh text eol=lf`. That line is done and not yet committed. Do not add it again.

| script | what it does | what it does not do |
|---|---|---|
| `env.sh` | sourced by all: paths, scratch `RUSTUP_HOME`/`CARGO_HOME`, plain PATH, `PKG_CONFIG_PATH`/`LIBCLANG_PATH` for the scratch sysroot | anything on its own |
| `00-install-rust.sh` | rustup + stable (minimal profile) into the scratch, `--no-modify-path` | sudo, edit dotfiles |
| `00-dev-libs.sh` | `apt-get download` (no root) of amd64 `libasound2-dev`, `libudev-dev`, `libclang1-21`, `libclang-common-21-dev`, unpacked into `scratch/sysroot`. This Ubuntu has only the `:i386` -dev packages and sudo needs a password | install into the system |
| `vkprobe.py` | lists Vulkan devices through `libvulkan.so.1` with ctypes (no vulkan-tools needed), per device; CPU type or llvmpipe/lavapipe never counts | create a device, draw |
| `01-check.sh` | tools, Python version, pins, disk, Vulkan devices (for information: builds need no GPU). Creates `$HOME/<game key>-wsl-scratch/logs` (not read-only) | build, run, compact, call engine.py |
| `02-time-builds.sh` | copies engine into ext4 scratch, times direct cargo, optionally (`FE_WSL_ROM` set) the capture library into `build/harness-wsl`, then the same 3dsrecomp command into `scratch/harness-ext4` (deleted right after) | run unless `FE_WSL_GPU_OK=1`; call engine.py; write engine/ or build/harness/lib |
| `03-time-headless.sh` | records whether a real Vulkan device and a Linux `examples/boot` exist | launch anything; call headless.py |
| `04-measure-vhdx.sh` | `df`, scratch size, and prints the compact commands | shut WSL down; compact |

## Compact

Printed by `04`, not run by it. Inside the guest, `sudo fstrim -av` first (needs the Linux sudo password). `Optimize-VHD` and diskpart need an elevated (admin) prompt. Then, from Windows, after every trial process has exited: `wsl --shutdown`. Find the vhdx from the Lxss registry `BasePath` for this distro (do not guess a Store path). Then either `Optimize-VHD -Mode Full`, or diskpart `compact vdisk` if the Hyper-V module is absent. `wsl --manage <distro> --set-sparse true` is the other way to keep the file from growing without a manual compact. Never compact while `02` or `03` is running.

## Results 2026-11-10

Run once by Claude while nothing else was using the machine (no boot.exe, 3dsrecomp.exe, replay.exe or game exe running). Machine: 24 threads. WSL2 Ubuntu 26.04.1, kernel 6.18.58, 15 GiB RAM. rustc 1.99.1 in WSL (the Windows record says 1.98.1).

Fixes made before and during the run (all in this folder):
- `01` aborted under `set -e` when the Vulkan check failed, before it printed FAIL.
- The Vulkan parser split on "GPU", which also appears in `DISCRETE_GPU`. It is now `vkprobe.py`, per device. `vulkaninfo` is not installed and needs sudo, so the probe uses the loader directly.
- The two GitHub git dependencies would have been downloaded. They are now served from the Windows cargo cache (see Builds).
- The Windows PATH leaked in through interop.
- The amd64 -dev headers were missing, and sudo needs a password. `00-dev-libs.sh` fixes that without root.
- The build had no time limit. It now has 90 minutes.
- Target dirs were reused, so a rerun timed an incremental build. They are now wiped each run.
- `cp -a` copied untracked files. It is now `git archive HEAD`.

Prerequisites (`01`): pass after `00-install-rust.sh`. Pins: zakuro HEAD 02a3e283 descends from c856685, and 3dsrecomp HEAD = df82e6e3. Linux git read the D: checkouts without a safe.directory change.

| step (clean build, warm crate cache) | WSL | Windows |
|---|---|---|
| cargo fetch from crates.io, first time / again | 5.8 s / 1.0 s | - |
| `cargo build --release --locked -p zakuro` (ext4) | 61.5 s | no clean measurement (engine builds are off limits in this task) |
| `-p zakuro-core --example boot` (ext4) | 48.0 s, 49.5 s | no clean measurement |
| 3dsrecomp, plain (ext4) | 3.0 s, 3.2 s | 6.1 s in build-record.json (not known to be clean) |
| capture library, `build.py --out build/harness-wsl` (output on D: through drvfs), build.py's own seconds | 135.6 s, 132.8 s (wall 139.0 s, 136.1 s) | 126.1 s, 126.5 s |
| the same 3dsrecomp command with the output in the Linux home (ext4) | 119.4 s inside 3dsrecomp, 124.0 s wall | 3dsrecomp's own line: 120.8 s, 121.0 s |

The first `zakuro` run failed (alsa-sys, then bindgen without libclang) until `00-dev-libs.sh` existed. The numbers above are the clean runs after it. The Linux library is a 90,621,256-byte `.so` (the Windows DLL is 80.7 MB). It was not loaded or run. `build/harness-wsl` (411 MB of generated C and objects) and the ext4 copy were deleted after the timing. `build/harness/lib` stays FRESH (`build.py --check-fresh`).

Vulkan (`vkprobe.py`): one device, `llvmpipe (LLVM 21.1.8)`, type CPU. There is no real device. `/dev/dxg` and the NVIDIA libraries exist, but no D3D12 Vulkan driver (dzn) is installed. So no headless game run was started in WSL (risk 20). A Linux `examples/boot` was built (ELF x86-64) and never launched.

Disk: the vhdx `D:\WSL\Ubuntu\ext4.vhdx` was 623,796,813,824 bytes before and 627,722,682,368 after (+3.66 GiB). It is not sparse. The distro is shared with other projects and was already 581 GB. The scratch `~/<game key>-wsl-scratch` is 4.6 GB (cargo-target 3.0 G, cargo-home 0.9 G, rustup 0.6 G, sysroot 48 M) and was left in place, since it is under 5 GB. Deleting it frees space inside the guest, but the vhdx does not shrink until a compact (`04` prints the steps; they were not run).

Verdict:

- Builds: WSL is not clearly faster. The capture library takes 124 s with its output on ext4, against 126 s on Windows (3dsrecomp's own part: 119 s against 121 s). With the output on D: through drvfs it takes 133-136 s, which is slower. A gain under 5% is noise, and getting it would mean keeping the output in the Linux home. The cargo builds are quick on Linux (zakuro 62 s, boot 48 s, clean), but there is no clean Windows number to compare them with. Moving builds is not worth it.
- Headless runs: not usable now. The only Vulkan device is llvmpipe (CPU), and risk 20 rules that out for save-load runs. headless.py also only launches the Windows boot.exe. Using WSL would first need a real GPU in WSL (a dzn driver, which needs sudo to install) and a `--boot` flag.
- Stay on Windows for both.

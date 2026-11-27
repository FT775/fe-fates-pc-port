#!/usr/bin/env bash
# The x86_64 -dev packages Zakuro's alsa-sys / libudev-sys need, plus libclang for bindgen
# (v4l2-sys-mit; matches the installed libllvm21), WITHOUT sudo: this Ubuntu has only
# the :i386 -dev packages, and installing amd64 ones needs the Linux sudo password. apt-get download
# (no root) fetches the .debs from the configured Ubuntu archive; dpkg-deb -x unpacks them into the
# scratch; the .pc files and .so links are pointed at the scratch headers and the system runtime libs.
# Writes only under ${SCRATCH}. Nothing is installed into the system.
set -euo pipefail
source "$(dirname "$0")/env.sh"
SR="${SCRATCH}/sysroot"
DEBS="${SCRATCH}/debs"
rm -rf "${SR}" "${DEBS}"
mkdir -p "${SR}" "${DEBS}"
( cd "${DEBS}" && apt-get download libasound2-dev:amd64 libudev-dev:amd64 libclang1-21:amd64 libclang-common-21-dev:amd64 )
for d in "${DEBS}"/*.deb; do dpkg-deb -x "${d}" "${SR}"; echo "unpacked $(basename "${d}")"; done
LIB="${SR}/usr/lib/x86_64-linux-gnu"
for so in "${LIB}"/*.so; do
  [[ -L "${so}" ]] || continue
  [[ -e "${so}" ]] && continue   # resolves inside the scratch already
  tgt="$(readlink "${so}")"
  if [[ -e "/usr/lib/x86_64-linux-gnu/${tgt##*/}" ]]; then
    ln -sfn "/usr/lib/x86_64-linux-gnu/${tgt##*/}" "${so}"
    echo "link $(basename "${so}") -> /usr/lib/x86_64-linux-gnu/${tgt##*/}"
  else
    echo "missing runtime lib for $(basename "${so}") (${tgt})"; exit 1
  fi
done
sed -i "s|^prefix=/usr\$|prefix=${SR}/usr|" "${LIB}"/pkgconfig/*.pc
rm -rf "${DEBS}"
PKG_CONFIG_PATH="${LIB}/pkgconfig" pkg-config --libs --cflags alsa libudev

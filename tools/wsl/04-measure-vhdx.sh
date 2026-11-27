#!/usr/bin/env bash
# Measure guest disk use and print compact commands. Does not shut WSL down.
set -euo pipefail

source "$(dirname "$0")/env.sh"
echo "home df:"
df -h "${HOME}"
echo "scratch:"
if [[ -d "${SCRATCH}" ]]; then
  du -sh "${SCRATCH}" || true
else
  echo "no scratch directory yet"
fi

echo
echo "Inside the guest, before compacting, and only when 02 and 03 are finished:"
echo "  sudo fstrim -av      (needs the Linux sudo password)"
echo
echo "Then from Windows, not from here:"
echo "  wsl --shutdown"
echo "  Find this distro's ext4.vhdx from the Lxss registry BasePath, and its size:"
echo "    Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss | Get-ItemProperty | Select DistributionName,BasePath"
echo "    (Get-Item \"<BasePath>\ext4.vhdx\").Length"
echo "  Do not guess a Store package path."
echo "  PowerShell, if the Hyper-V module is present:"
echo "    Optimize-VHD -Path \"<BasePath>\\ext4.vhdx\" -Mode Full"
echo "  Otherwise diskpart:"
echo "    select vdisk file=\"<BasePath>\\ext4.vhdx\""
echo "    attach vdisk readonly"
echo "    compact vdisk"
echo "    detach vdisk"
echo "  Optional, from Windows, to limit later growth:"
echo "    wsl --manage <distro> --set-sparse true"
echo
echo "compact: not run."

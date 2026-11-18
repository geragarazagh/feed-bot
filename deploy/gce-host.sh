#!/bin/sh
# One-time host tuning for a Google Cloud e2-micro (1 GB RAM) running Debian. Run as root.
set -eu
# TPM2 libraries: systemd-creds seals the secrets to the VM's virtual TPM (Shielded VM).
apt-get install -y -q libtss2-esys-3.0.2-0t64 libtss2-rc0t64 libtss2-mu-4.0.1-0t64 >/dev/null
# 1 GB swap file: headroom for apt upgrades on a 1 GB machine (lives on the free 30 GB disk).
if [ ! -e /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a
echo 'vm.swappiness=10' > /etc/sysctl.d/90-swappiness.conf && sysctl -q --system
# Security updates are already on in Google's Debian images (unattended-upgrades); let them reboot
# when a kernel update needs it, at 00:30 UTC (02:30-03:30 in Kyiv), when nobody reads the feed.
cat > /etc/apt/apt.conf.d/52tgfeed-reboot <<'CONF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "00:30";
CONF
# VM Manager's agent: unused here (its API is off) and the largest process on the box.
systemctl disable --now google-osconfig-agent 2>/dev/null || true
# Keep the journal small.
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=200M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald

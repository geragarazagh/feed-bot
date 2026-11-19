#!/bin/sh
# Install or update the bot on a Debian/Ubuntu server. Run as root from the unpacked source:
#   sudo sh deploy/install.sh
# The first install also needs, made as root before this script:
#   /etc/feedbot/config.json   {"max_channels": 100, "ipv6_only": false, "status_bucket": ""}
#                              (ipv6_only: true on a host with IPv6 but no IPv4 route; other settings: tgfeed/config.py)
#   /etc/feedbot/token.cred    printf '%s' 'BOT_TOKEN' | systemd-creds encrypt --with-key=host+tpm2 --name=token - /etc/feedbot/token.cred
#                              (--with-key=host on a machine without a TPM)
set -eu
SRC=$(cd "$(dirname "$0")/.." && pwd)

DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv >/dev/null
id feedbot >/dev/null 2>&1 || useradd --system --home-dir /var/lib/feedbot --shell /usr/sbin/nologin feedbot

install -d -m 0755 /opt/feedbot
rm -rf /opt/feedbot/src.new
cp -a "$SRC" /opt/feedbot/src.new
rm -rf /opt/feedbot/src
mv /opt/feedbot/src.new /opt/feedbot/src
[ -x /opt/feedbot/venv/bin/python ] || python3 -m venv /opt/feedbot/venv
/opt/feedbot/venv/bin/pip install -q --upgrade pip
/opt/feedbot/venv/bin/pip install -q "/opt/feedbot/src"
ln -sf /opt/feedbot/venv/bin/feedbot-admin /usr/local/bin/feedbot-admin

install -m 0644 "$SRC/deploy/feedbot.service" /etc/systemd/system/feedbot.service
systemctl daemon-reload
systemctl enable feedbot >/dev/null
systemctl restart feedbot
systemctl --no-pager --lines=0 status feedbot | head -3

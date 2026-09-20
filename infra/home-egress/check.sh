#!/usr/bin/env bash
# Non-destructive health check for the residential Tailscale/Dante node.
set -euo pipefail

echo "== services =="
systemctl is-enabled tailscaled danted mochila-render-danted-config.service
systemctl is-active tailscaled danted

echo "== tailnet IPv4 =="
tailscale ip -4

echo "== SOCKS listener (must be tailscale0:1080 only) =="
ss -ltnp '( sport = :1080 )'

echo "== configured Hetzner source =="
sed 's/$/\/32/' /etc/mochila-home-egress/hetzner-tailscale-ip

echo "== residential public IPv4 (record for Hetzner verification only) =="
curl -4fsS --max-time 15 https://api.ipify.org
echo

echo "== recent Dante logs =="
journalctl -u danted --no-pager -n 30

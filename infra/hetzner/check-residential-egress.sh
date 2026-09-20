#!/usr/bin/env bash
# Validates the required public-IP equality from Hetzner and from the real worker.
# Run on the Hetzner host after setting HOME_PUBLIC_IP from the home check script.
set -euo pipefail

usage() {
  echo "Usage: HOME_PUBLIC_IP=203.0.113.10 $0 <home-tailscale-host-or-ip>" >&2
  exit 2
}

: "${HOME_PUBLIC_IP:?Set HOME_PUBLIC_IP to the value printed by home-egress/check.sh}"
home_proxy="${1:-}"
[[ -n "${home_proxy}" ]] || usage

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${here}"

public_ip() {
  curl -4fsS --max-time 20 https://api.ipify.org
}

proxy_ip() {
  curl -4fsS --max-time 20 --socks5-hostname "${home_proxy}:1080" https://api.ipify.org
}

echo "== tailnet peer =="
tailscale ping --timeout=10s "${home_proxy}"

hetzner_direct="$(public_ip)"
hetzner_socks="$(proxy_ip)"
worker_socks="$(docker compose exec -T worker sh -ceu \
  'curl -4fsS --max-time 20 --socks5-hostname "$1:1080" https://api.ipify.org' \
  sh "${home_proxy}")"

printf 'HOME_PUBLIC_IP=%s\n' "${HOME_PUBLIC_IP}"
printf 'DIRECT_FROM_HETZNER=%s\n' "${hetzner_direct}"
printf 'SOCKS_FROM_HETZNER=%s\n' "${hetzner_socks}"
printf 'SOCKS_FROM_WORKER=%s\n' "${worker_socks}"

if [[ "${hetzner_direct}" == "${HOME_PUBLIC_IP}" ]]; then
  echo "FAIL: Hetzner direct egress unexpectedly equals the residential IP" >&2
  exit 1
fi
if [[ "${hetzner_socks}" != "${HOME_PUBLIC_IP}" ]]; then
  echo "FAIL: host SOCKS egress does not equal HOME_PUBLIC_IP" >&2
  exit 1
fi
if [[ "${worker_socks}" != "${HOME_PUBLIC_IP}" ]]; then
  echo "FAIL: worker SOCKS egress does not equal HOME_PUBLIC_IP" >&2
  exit 1
fi

echo "PASS: worker -> SOCKS over Tailscale -> residential public IP"

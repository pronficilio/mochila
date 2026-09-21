#!/usr/bin/env bash
# Render the Dante configuration after Tailscale and the normal WAN route exist.
set -euo pipefail

hetzner_ip=""
if [[ -r /etc/mochila-home-egress/hetzner-tailscale-ip ]]; then
  IFS= read -r hetzner_ip < /etc/mochila-home-egress/hetzner-tailscale-ip || true
fi
if [[ ! "${hetzner_ip}" =~ ^100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  echo "Unable to determine authorized Hetzner Tailscale IP" >&2
  exit 1
fi

# WSL2 exposes the residential default route as an ordinary Linux route (usually
# eth0). Read its device field; neither the device nor a WAN address is hardcoded.
default_route="$(ip -4 route show default 2>/dev/null || true)"
egress_interface="$(awk '$1 == "default" && $5 != "" { print $5; exit }' <<<"${default_route}")"
if [[ -z "${egress_interface}" ]] \
  || ! ip link show dev "${egress_interface}" >/dev/null 2>&1; then
  echo "Unable to determine residential egress interface" >&2
  exit 1
fi
if ! ip link show tailscale0 >/dev/null 2>&1; then
  echo "tailscale0 is not available" >&2
  exit 1
fi

umask 077
temporary_config="$(mktemp /etc/danted.conf.tmp.XXXXXX)"
trap 'rm -f "${temporary_config}"' EXIT
{
  printf '%s\n' \
    'logoutput: syslog' \
    'internal: tailscale0 port = 1080' \
    'external.protocol: ipv4' \
    "external: ${egress_interface}" \
    '' \
    'clientmethod: none' \
    'socksmethod: none' \
    '' \
    'user.privileged: proxy' \
    'user.notprivileged: nobody' \
    'user.libwrap: nobody' \
    '' \
    '# Only the Hetzner tailnet node may open a SOCKS connection.' \
    'client pass {' \
    "    from: ${hetzner_ip}/32 to: 0.0.0.0/0" \
    '    log: connect error' \
    '}' \
    'client block {' \
    '    from: 0.0.0.0/0 to: 0.0.0.0/0' \
    '    log: connect error' \
    '}' \
    '' \
    '# Hetzner can proxy TCP and UDP to the public Internet, never the tailnet.' \
    'socks pass {' \
    "    from: ${hetzner_ip}/32 to: 0.0.0.0/0" \
    '    command: connect udpassociate' \
    '    log: connect error' \
    '}' \
    'socks block {' \
    '    from: 0.0.0.0/0 to: 0.0.0.0/0' \
    '    log: connect error' \
    '}'
} >"${temporary_config}"
install -m 0600 "${temporary_config}" /etc/danted.conf

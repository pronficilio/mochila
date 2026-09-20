#!/usr/bin/env bash
# Installs a tailnet-only Dante SOCKS listener on Debian or Ubuntu.
# Run as root, with HETZNER_TAILSCALE_IP set to Hetzner's 100.x address.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo env HETZNER_TAILSCALE_IP=100.x.y.z $0" >&2
  exit 1
fi

: "${HETZNER_TAILSCALE_IP:?Set Hetzner's Tailscale IPv4 address, e.g. 100.64.0.20}"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-home-mini}"

if [[ ! "${HETZNER_TAILSCALE_IP}" =~ ^100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  echo "HETZNER_TAILSCALE_IP must be a 100.x.y.z Tailscale IPv4 address" >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Only Debian and Ubuntu are supported by this installer" >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release
ID="${ID:-}"
VERSION_CODENAME="${VERSION_CODENAME:-}"
if [[ "${ID}" != "debian" && "${ID}" != "ubuntu" ]]; then
  echo "Only Debian and Ubuntu are supported by this installer" >&2
  exit 1
fi
: "${VERSION_CODENAME:?Unable to identify the Debian/Ubuntu release codename}"

install_tailscale() {
  if command -v tailscale >/dev/null 2>&1; then
    return
  fi

  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl gnupg
  install -d -m 0755 /usr/share/keyrings
  curl -fsSL \
    "https://pkgs.tailscale.com/stable/${ID}/${VERSION_CODENAME}.noarmor.gpg" \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  printf 'deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/%s %s main\n' \
    "${ID}" "${VERSION_CODENAME}" \
    >/etc/apt/sources.list.d/tailscale.list
  apt-get update
  apt-get install -y --no-install-recommends tailscale
}

install_tailscale
apt-get update
if ! dpkg-query -W -f='${db:Status-Status}' dante-server 2>/dev/null | grep -qx installed; then
  # Do not let the package post-install hook start Dante with its distribution
  # default configuration before the tailnet-only configuration exists.
  systemctl mask danted.service
  apt-get install -y --no-install-recommends dante-server curl iproute2
else
  apt-get install -y --no-install-recommends dante-server curl iproute2
fi
# A previous interrupted run may have installed the package while it was masked.
# Unmasking does not start it; it only permits the configured start below.
systemctl unmask danted.service

install -d -m 0755 /etc/mochila-home-egress /etc/systemd/system/danted.service.d
printf '%s\n' "${HETZNER_TAILSCALE_IP}" >/etc/mochila-home-egress/hetzner-tailscale-ip

cat >/usr/local/sbin/mochila-render-danted-config <<'EOF'
#!/usr/bin/env bash
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
# eth0). Select the interface field from that route; never hardcode its name.
egress_interface=""
egress_interface="$(ip -4 route show default 2>/dev/null \
  | awk '$1 == "default" && $5 != "" { print $5; exit }' || true)"
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
cat >/etc/danted.conf <<CONFIG
logoutput: syslog
internal: tailscale0 port = 1080
external: ${egress_interface}

clientmethod: none
socksmethod: none

user.privileged: proxy
user.notprivileged: nobody
user.libwrap: nobody

# Only the Hetzner tailnet node may open a SOCKS connection.
client pass {
    from: ${hetzner_ip}/32 to: 0.0.0.0/0
    log: connect error
}
client block {
    from: 0.0.0.0/0 to: 0.0.0.0/0
    log: connect error
}

# Hetzner can proxy TCP and UDP to the public Internet, never the tailnet.
socks pass {
    from: ${hetzner_ip}/32 to: 0.0.0.0/0
    command: connect udpassociate
    log: connect error
}
socks block {
    from: 0.0.0.0/0 to: 0.0.0.0/0
    log: connect error
}
CONFIG
EOF
chmod 0755 /usr/local/sbin/mochila-render-danted-config

cat >/etc/systemd/system/mochila-render-danted-config.service <<'EOF'
[Unit]
Description=Render Dante configuration for Mochila residential egress
Wants=network-online.target tailscaled.service
After=network-online.target tailscaled.service
Before=danted.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/mochila-render-danted-config

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/danted.service.d/mochila.conf <<'EOF'
[Unit]
Wants=network-online.target tailscaled.service mochila-render-danted-config.service
After=network-online.target tailscaled.service mochila-render-danted-config.service
Requires=mochila-render-danted-config.service

[Service]
Restart=always
RestartSec=5
EOF

systemctl daemon-reload
systemctl enable --now tailscaled

if [[ -n "${TAILSCALE_AUTHKEY:-}" ]]; then
  # The key is consumed by tailscale; it is never written by this script.
  tailscale up --hostname="${TAILSCALE_HOSTNAME}" --auth-key="${TAILSCALE_AUTHKEY}"
else
  echo "Authenticate this node in the displayed Tailscale URL (or rerun with TAILSCALE_AUTHKEY)."
  tailscale up --hostname="${TAILSCALE_HOSTNAME}"
fi

systemctl enable mochila-render-danted-config.service danted.service
systemctl restart mochila-render-danted-config.service
systemctl restart danted.service

echo
echo "Home Tailscale IPv4: $(tailscale ip -4)"
echo "Dante is bound only to tailscale0:1080 and only accepts ${HETZNER_TAILSCALE_IP}."
echo "Run infra/home-egress/check.sh to inspect its state."

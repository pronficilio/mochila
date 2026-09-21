#!/usr/bin/env bash
# Installs a tailnet-only Dante SOCKS listener on Debian or Ubuntu.
# Run as root, with HETZNER_TAILSCALE_IP set to Hetzner's 100.x address.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo env HETZNER_TAILSCALE_IP=100.x.y.z $0" >&2
  exit 1
fi

: "${HETZNER_TAILSCALE_IP:?Set the Hetzner Tailscale IPv4 address, e.g. 100.64.0.20}"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-home-mini}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RENDERER_SOURCE="${SCRIPT_DIR}/render-danted-config.sh"
GAI_SOURCE="${SCRIPT_DIR}/danted-gai.conf"
DANTED_DROPIN_SOURCE="${SCRIPT_DIR}/danted.service.d/mochila.conf"

if [[ ! "${HETZNER_TAILSCALE_IP}" =~ ^100\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
  echo "HETZNER_TAILSCALE_IP must be a 100.x.y.z Tailscale IPv4 address" >&2
  exit 1
fi
for source in "${RENDERER_SOURCE}" "${GAI_SOURCE}" "${DANTED_DROPIN_SOURCE}"; do
  if [[ ! -f "${source}" ]]; then
    echo "Missing infrastructure source: ${source}" >&2
    exit 1
  fi
done

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
install -m 0755 "${RENDERER_SOURCE}" /usr/local/sbin/mochila-render-danted-config
install -m 0644 "${GAI_SOURCE}" /etc/mochila-home-egress/danted-gai.conf

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

install -m 0644 "${DANTED_DROPIN_SOURCE}" /etc/systemd/system/danted.service.d/mochila.conf

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

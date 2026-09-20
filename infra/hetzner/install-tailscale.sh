#!/usr/bin/env bash
# Installs and enables Tailscale on Debian/Ubuntu Hetzner hosts.
# Enrol with TAILSCALE_AUTHKEY in the environment, or complete the printed URL.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-hetzner}"

if ! command -v tailscale >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "debian" && "${ID:-}" != "ubuntu" ]]; then
    echo "Only Debian and Ubuntu are supported by this installer" >&2
    exit 1
  fi
  : "${VERSION_CODENAME:?Unable to identify the Debian/Ubuntu release codename}"
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
fi

systemctl enable --now tailscaled

if tailscale status --json 2>/dev/null | grep -q '"BackendState":"Running"'; then
  echo "Tailscale is already connected: $(tailscale ip -4)"
  exit 0
fi

if [[ -n "${TAILSCALE_AUTHKEY:-}" ]]; then
  # The key is never written by this script.
  tailscale up --hostname="${TAILSCALE_HOSTNAME}" --auth-key="${TAILSCALE_AUTHKEY}"
else
  echo "Complete enrolment in the URL printed next (or rerun with TAILSCALE_AUTHKEY)."
  tailscale up --hostname="${TAILSCALE_HOSTNAME}"
fi

echo "Hetzner Tailscale IPv4: $(tailscale ip -4)"

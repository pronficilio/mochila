#!/usr/bin/env bash
# Apply or roll back the danted-only IPv4 resolver policy. Run as root.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="/etc/mochila-home-egress"
DROPIN_DIR="/etc/systemd/system/danted.service.d"
RENDERER_SOURCE="${SCRIPT_DIR}/render-danted-config.sh"
GAI_SOURCE="${SCRIPT_DIR}/danted-gai.conf"
DROPIN_SOURCE="${SCRIPT_DIR}/danted.service.d/mochila.conf"
RENDERER_TARGET="/usr/local/sbin/mochila-render-danted-config"
GAI_TARGET="${STATE_DIR}/danted-gai.conf"
DROPIN_TARGET="${DROPIN_DIR}/mochila.conf"
CONFIG_TARGET="/etc/danted.conf"

usage() {
  echo "Usage: $0 [--rollback BACKUP_DIRECTORY]" >&2
  exit 2
}

restore_backup() {
  local backup_dir="$1"
  local target="$2"
  local name="$3"
  if [[ -e "${backup_dir}/${name}.absent" ]]; then
    rm -f -- "${target}"
  else
    cp -a -- "${backup_dir}/${name}" "${target}"
  fi
}

if [[ "${1:-}" == "--rollback" ]]; then
  [[ "$#" == 2 ]] || usage
  backup_dir="$2"
  [[ -d "${backup_dir}" ]] || { echo "Backup directory not found: ${backup_dir}" >&2; exit 1; }

  restore_backup "${backup_dir}" "${RENDERER_TARGET}" renderer
  restore_backup "${backup_dir}" "${GAI_TARGET}" danted-gai.conf
  restore_backup "${backup_dir}" "${DROPIN_TARGET}" mochila.conf
  restore_backup "${backup_dir}" "${CONFIG_TARGET}" danted.conf
  systemctl daemon-reload
  systemctl restart danted.service
  systemctl is-active --quiet danted.service
  echo "Rolled back danted IPv4 policy from ${backup_dir}"
  exit 0
fi
[[ "$#" == 0 ]] || usage

for source in "${RENDERER_SOURCE}" "${GAI_SOURCE}" "${DROPIN_SOURCE}"; do
  [[ -f "${source}" ]] || { echo "Missing source: ${source}" >&2; exit 1; }
done

backup_dir="${STATE_DIR}/backups/danted-ipv4-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0755 "${backup_dir}" "${DROPIN_DIR}"

backup_file() {
  local target="$1"
  local name="$2"
  if [[ -e "${target}" ]]; then
    cp -a -- "${target}" "${backup_dir}/${name}"
  else
    : >"${backup_dir}/${name}.absent"
  fi
}

backup_file "${RENDERER_TARGET}" renderer
backup_file "${GAI_TARGET}" danted-gai.conf
backup_file "${DROPIN_TARGET}" mochila.conf
backup_file "${CONFIG_TARGET}" danted.conf

rollback_needed=1
rollback_on_error() {
  local status="$?"
  if [[ "${rollback_needed}" == 1 ]]; then
    set +e
    restore_backup "${backup_dir}" "${RENDERER_TARGET}" renderer
    restore_backup "${backup_dir}" "${GAI_TARGET}" danted-gai.conf
    restore_backup "${backup_dir}" "${DROPIN_TARGET}" mochila.conf
    restore_backup "${backup_dir}" "${CONFIG_TARGET}" danted.conf
    systemctl daemon-reload
    systemctl restart danted.service
    echo "Apply failed; restored danted configuration from ${backup_dir}" >&2
  fi
  exit "${status}"
}
trap rollback_on_error ERR

install -m 0755 "${RENDERER_SOURCE}" "${RENDERER_TARGET}"
install -m 0644 "${GAI_SOURCE}" "${GAI_TARGET}"
install -m 0644 "${DROPIN_SOURCE}" "${DROPIN_TARGET}"
systemctl daemon-reload
systemctl restart mochila-render-danted-config.service
systemctl restart danted.service
systemctl is-active --quiet danted.service

main_pid="$(systemctl show --value --property MainPID danted.service)"
[[ "${main_pid}" =~ ^[1-9][0-9]*$ ]] || { echo "Unable to determine danted MainPID" >&2; exit 1; }
nsenter -t "${main_pid}" -m grep -Fqx 'precedence ::ffff:0:0/96 100' /etc/gai.conf

rollback_needed=0
echo "Applied danted-only IPv4 resolver policy"
echo "Backup: ${backup_dir}"
echo "Rollback: sudo ${SCRIPT_DIR}/apply-danted-ipv4-policy.sh --rollback ${backup_dir}"

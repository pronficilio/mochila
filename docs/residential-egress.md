# Residential YouTube egress

This route is deliberately narrow: `Mochila worker on Hetzner -> SOCKS5 over
Tailscale -> home-mini -> residential WAN -> YouTube`. FastAPI, Redis, output
files, and all normal Hetzner/Docker traffic remain on Hetzner. Only `yt-dlp`
receives the proxy argument and residential mode never falls back to direct egress.

The scripts target Debian/Ubuntu. Never commit a Tailscale auth key, public WAN IP,
or proxy credentials. `tailscaled` persists its node state, starts at boot and
reconnects after a dynamic residential WAN address changes or recovers. Mochila
stores the stable tailnet address only; deleting/re-enrolling a node can change it.

## Enrol both nodes

On Hetzner, run the idempotent installer, then complete its one-time Tailscale
enrolment. It can receive `TAILSCALE_AUTHKEY` only through its process environment
for non-interactive enrolment:

```bash
sudo ./infra/hetzner/install-tailscale.sh
tailscale ip -4
```

Use the home installer below for `home-mini`. MagicDNS names are convenient on the
host, but Docker may not resolve them, so use the home node's `100.x.y.z` address in
`RESIDENTIAL_PROXY` unless the worker test proves its name resolves.

## Home-mini: locked-down Dante

Find Hetzner's Tailscale IPv4, copy this repository (or `infra/home-egress`) to the
home machine, then run:

```bash
sudo env HETZNER_TAILSCALE_IP=100.x.y.z TAILSCALE_HOSTNAME=home-mini ./infra/home-egress/install.sh
```

The idempotent installer installs Tailscale if absent, installs `dante-server`,
detects the normal IPv4 default-route interface, and enables `tailscaled`, a boot
renderer and `danted`. Supply `TAILSCALE_AUTHKEY` only in the command environment
for non-interactive enrolment; the script never writes it. Without it, `tailscale
up` displays the one-time enrolment URL.

The generated policy binds only `tailscale0:1080`, allows only
`HETZNER_TAILSCALE_IP/32`, and sends proxy traffic to the normal residential default
route. Internet cannot reach port 1080 because no public interface listens on it.
Verify the exact listener and record its temporary comparison value:

```bash
./infra/home-egress/check.sh
```

The listener must show `tailscale0`/`100.x`, never `0.0.0.0:1080` or a WAN address.
If UFW is used, add defence in depth but never open 1080 globally:

```bash
sudo ufw allow in on tailscale0 from 100.x.y.z to any port 1080 proto tcp
sudo ufw deny in 1080/tcp
```

Put the allow rule before the deny rule. Binding plus Dante's `/32` rule remain the
primary protection.

## Tailnet ACL

Add this narrow fragment to an existing Tailscale ACL policy (adapt tags/owners; do
not replace the policy):

```json
{"tagOwners":{"tag:mochila-hetzner":["autogroup:admin"],"tag:mochila-home":["autogroup:admin"]},"acls":[{"action":"accept","src":["tag:mochila-hetzner"],"dst":["tag:mochila-home:1080"]}]}
```

## Mandatory public-IP gate

Take `HOME_PUBLIC_IP` only from the home check output and run this on Hetzner from
the repository root:

```bash
HOME_PUBLIC_IP=THE_VALUE_FROM_HOME ./infra/hetzner/check-residential-egress.sh 100.x.y.z
```

It checks the Tailscale peer, direct Hetzner egress, SOCKS from Hetzner, and SOCKS
from the actual worker container. It exits non-zero unless:

```text
DIRECT_FROM_HETZNER != HOME_PUBLIC_IP
SOCKS_FROM_HETZNER == HOME_PUBLIC_IP
SOCKS_FROM_WORKER == HOME_PUBLIC_IP
```

Do not activate residential mode before this passes.

## Enable Mochila after passing the gate

Edit `/opt/mochila/.env` using the home Tailscale address, never its WAN address:

```dotenv
DOWNLOAD_EGRESS=residential
RESIDENTIAL_PROXY=socks5h://100.x.y.z:1080
```

`socks5h` routes YouTube DNS resolution too. Recreate only consumers:

```bash
cd /opt/mochila && docker compose up -d --build api worker
```

After normal Mochila login, check the authenticated endpoint:

```bash
curl -b cookies.txt -sS https://178.105.138.91/v1/egress
```

It must return `{"mode":"residential","configured":true,"reachable":true}`
without revealing the proxy. This is a Mochila cookie, not a YouTube cookie.

Submit a small public video in the normal UI and inspect the worker with `cd
/opt/mochila && docker compose logs --tail=100 worker`. Its argv must contain
`--proxy socks5h://100.x.y.z:1080`; success is `queued`, `running`, then `done` with
the final file stored in Hetzner. If YouTube still returns bot verification, retain
the worker output and stop: this deliberately adds no cookies, Google account, PO
token, or direct fallback. Home reboot starts `tailscaled`, renderer and `danted`;
when home-mini is offline Mochila fails promptly with `Residential egress is
unavailable`, never direct egress.

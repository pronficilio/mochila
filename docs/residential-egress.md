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
up` displays the one-time enrolment URL. During its first package installation it
temporarily masks `danted`, so the distribution's default configuration never gets
a chance to listen before the tailnet-only configuration is written.

Keep `install.sh` and `render-danted-config.sh` together: the installer validates
the renderer is present before it changes packages or services.

The installer supports Ubuntu under WSL2/systemd: it reads the Linux IPv4 default
route (for example, `default via ... dev eth0`) and uses that route's interface as
Dante's outbound interface. It does not hardcode `eth0`; if no valid default-route
interface exists, it stops with `Unable to determine residential egress interface`.

The generated policy binds only `tailscale0:1080`, allows only
`HETZNER_TAILSCALE_IP/32`, and sends proxy traffic to the normal residential IPv4
default route. It emits `external.protocol: ipv4` immediately before the detected
`external:` interface. This is deliberate: WSL2/home networks can resolve AAAA
records while lacking usable IPv6 Internet routing. Internet cannot reach port 1080
because no public interface listens on it. Verify the exact listener and record its
temporary comparison value:

```bash
./infra/home-egress/check.sh
```

The listener must show `tailscale0`/`100.x`, never `0.0.0.0:1080` or a WAN address.
Mochila uses a small yt-dlp wrapper in residential mode to preserve the local DNS
semantics of `socks5://`; it resolves IPv4 on the worker before connecting through
Dante. Dante therefore needs no private resolver configuration, and `/etc/gai.conf`,
DNS, Windows and WSL networking remain unchanged.
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

This IP comparison is necessary but not a complete YouTube health check: it proves
basic IPv4 egress through the SOCKS listener, not a Googlevideo CDN transfer. After
any egress infrastructure change, also run a small public YouTube download through
Mochila. A future automated YouTube smoke test must cover extraction and a real CDN
transfer through SOCKS; `api.ipify.org` alone is insufficient.

## Enable Mochila after passing the gate

Edit `/opt/mochila/.env` using the home Tailscale address, never its WAN address:

```dotenv
DOWNLOAD_EGRESS=residential
RESIDENTIAL_PROXY=socks5://100.x.y.z:1080
```

Residential mode resolves YouTube names in Hetzner, forces IPv4 in yt-dlp, and sends
the resulting TCP/media connections through the SOCKS listener. Recreate only
consumers:

```bash
cd /opt/mochila && docker compose up -d --build api worker
```

After normal Mochila login, check the authenticated endpoint:

```bash
curl -b cookies.txt -sS https://178.105.138.91/v1/egress
```

It must return `{"mode":"residential","configured":true,"reachable":true}`
without revealing the proxy. This is a Mochila cookie, not a YouTube cookie.

Residential downloads also use yt-dlp `mweb` with the private BgUtils automatic PO
Token provider. The provider gets the configured SOCKS route from yt-dlp; it has no
published host port and does not use a Google account or cookies. See the
"PO Tokens automáticos para YouTube" section in the README for the exact arguments.

Submit a small public video in the normal UI and inspect the worker with `cd
/opt/mochila && docker compose logs --tail=100 worker`. Its argv must contain
`--force-ipv4 --proxy socks5://100.x.y.z:1080` plus `mweb` and the private PO
provider extractor arguments; success is `queued`, `running`, then
`done` with the final file stored in Hetzner. If YouTube still returns bot verification, retain
the worker output and stop: this deliberately adds no cookies, Google account, PO
token, or direct fallback. Home reboot starts `tailscaled` and `danted`;
when home-mini is offline Mochila fails promptly with `Residential egress is
unavailable`, never direct egress.

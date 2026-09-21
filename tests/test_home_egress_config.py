import os
import subprocess
from pathlib import Path


def test_rendered_dante_config_forces_ipv4_egress(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    source = repository / "infra/home-egress/render-danted-config.sh"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "hetzner-tailscale-ip").write_text("100.79.223.101\n")
    config_path = tmp_path / "danted.conf"

    renderer = tmp_path / "render-danted-config.sh"
    renderer.write_text(
        source.read_text()
        .replace("/etc/mochila-home-egress", str(state_dir))
        .replace("/etc/danted.conf", str(config_path))
    )
    renderer.chmod(0o755)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ip = fake_bin / "ip"
    fake_ip.write_text(
        "#!/usr/bin/env sh\n"
        "case \"$*\" in\n"
        "  '-4 route show default') echo 'default via 192.0.2.1 dev residential0' ;;\n"
        "  'link show dev residential0'|'link show tailscale0') exit 0 ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    fake_ip.chmod(0o755)

    environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}
    subprocess.run(["bash", str(renderer)], check=True, env=environment)

    lines = config_path.read_text().splitlines()
    protocol_line = lines.index("external.protocol: ipv4")
    external_line = lines.index("external: residential0")
    assert external_line == protocol_line + 1

#!/bin/sh
set -eu

project_dir="/opt/mochila"
cd "$project_dir"

docker compose stop proxy
restart_proxy() {
    docker compose start proxy
}
trap restart_proxy EXIT

docker run --rm \
    -p 80:80 \
    -v "$project_dir/certbot:/etc/letsencrypt" \
    certbot/certbot:latest renew \
    --cert-name mochila-ip \
    --standalone \
    --preferred-profile shortlived \
    --non-interactive

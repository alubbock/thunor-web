#!/usr/bin/env bash
# Renew TLS certificates on a Docker Machine instance
THUNORHOME="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
docker run --rm -v "THUNORHOME/_state/certbot:/etc/letsencrypt" \
    -v "$THUNORHOME/_state/.well-known:/thunor-static/.well-known" \
    certbot/certbot renew --non-interactive
docker exec $(docker ps --filter ancestor=nginx:mainline -q) nginx -s reload
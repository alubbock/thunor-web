#!/bin/bash
THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

: "${THUNORHOME:?"Need to set THUNORHOME environment variable"}"

docker-compose -f $THIS_DIR/docker-compose.services.yml run --rm --no-deps certbot certbot renew --non-interactive
docker-compose exec nginx nginx -s reload

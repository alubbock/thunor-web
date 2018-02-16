#!/bin/bash

set -e

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
THUNORHOME=${THUNORHOME:-.}

echo "generating dhparams.pem if required..."
#    docker-compose run --no-deps --rm -v ./_state/certbot:/certbot nginx openssl dhparam -out /certbot/dhparams.pem 2048
#docker-compose -f docker-compose.certbot.yml run certbot openssl dhparam -out /etc/letsencrypt/dhparams.pem 2048
docker-compose -f docker-compose.certbot.yml run --rm certbot sh -c "[[ -e /etc/letsencrypt/dhparams.pem ]] || openssl dhparam -out /etc/letsencrypt/dhparams.pem 2048"

docker-compose -f docker-compose.certbot.yml run --rm certbot certbot certonly --webroot --webroot-path /thunor-static "$@"

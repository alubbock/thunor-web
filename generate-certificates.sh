#!/bin/bash

set -e

: "${THUNORHOME:?"Need to set THUNORHOME environment variable"}"

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "generating dhparams.pem, if required..."
docker-compose -f $THIS_DIR/docker-compose.services.yml run --rm certbot sh -c "[[ -e /etc/letsencrypt/dhparams.pem ]] || openssl dhparam -out /etc/letsencrypt/dhparams.pem 2048"

echo "generating requested certificates..."
docker-compose -f $THIS_DIR/docker-compose.services.yml run --rm certbot certbot certonly --webroot --webroot-path /thunor-static "$@"

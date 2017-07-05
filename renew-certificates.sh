#!/bin/bash
THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
docker-compose -f $THIS_DIR/docker-compose.certbot.yml run --rm certbot certbot renew --non-interactive

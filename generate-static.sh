#!/bin/bash

set -e

: "${THUNORHOME:?"Need to set THUNORHOME environment variable"}"

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DEVFLAG=

if [ "$1" = "--dev" ]; then
  echo "Processing staticfiles outside of container; do not use in production"
  DEVFLAG="-e DJANGO_DEBUG=True"
fi

docker build -t thunor_webpack thunorweb/webpack
docker run --rm $DEVFLAG -v $THUNORHOME/_state/webpack-bundles:/_state/webpack-bundles thunor_webpack

if [ "$1" = "--dev" ]; then
  python $BASE_DIR/manage.py collectstatic --no-input
else
  docker-compose run --rm -v $THUNORHOME/_state/webpack-bundles:/thunor/_state/webpack-bundles -v $THUNORHOME/_state/thunor-static:/thunor/_state/thunor-static app python manage.py collectstatic --no-input || exit $?
  echo "Put changes live with 'docker-compose up -d --build app'"
fi

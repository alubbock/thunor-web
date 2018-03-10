#!/bin/bash

set -e

: "${THUNORHOME:?"Need to set THUNORHOME environment variable"}"

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ "$1" = "--no-container" ]; then
  echo "Processing staticfiles outside of container; do not use in production"
fi

docker build -t thunor_webpack thunorweb/webpack
docker run --rm -v $THUNORHOME/_state/webpack-bundles:/_state/webpack-bundles thunor_webpack

if [ "$1" = "--no-container" ]; then
  python $BASE_DIR/manage.py collectstatic --no-input
else
  docker-compose run --rm -v $THUNORHOME/_state/webpack-bundles:/thunor/_state/webpack-bundles -v $THUNORHOME/_state/thunor-static:/thunor/_state/thunor-static app python manage.py collectstatic --no-input || exit $?
  echo "Put changes live with 'docker-compose up -d --build app'"
fi

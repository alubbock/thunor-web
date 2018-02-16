#!/bin/bash

set -e

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
THUNORHOME=${THUNORHOME:-$BASE_DIR}

if [ "$1" = "--no-container" ]; then
  echo "Processing staticfiles outside of container; do not use in production"
  cd $BASE_DIR
  npm run build || exit 1
  cd -
  python $BASE_DIR/manage.py collectstatic --no-input --ignore thunorweb
else
  docker build -t thunor_webpack thunorweb/static
  docker run --rm -v $THUNORHOME/_state/webpack-bundles:/_state/webpack-bundles thunor_webpack || exit $?
  docker-compose -f $BASE_DIR/docker-compose.yml run --rm -v $THUNORHOME/_state/webpack-bundles:/thunor/_state/webpack-bundles -v $THUNORHOME/_state/thunor-static:/thunor/_state/thunor-static app python manage.py collectstatic --no-input --ignore thunorweb || exit $?
  echo "Put changes live with 'docker-compose up -d --build app'"
fi

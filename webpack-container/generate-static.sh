#!/bin/bash

set -e

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "${THIS_DIR}" )"
COLLECT_STATIC_ARGS="--no-input --ignore pyhts"

if [ "$1" = "--no-container" ]; then
  echo "Processing staticfiles outside of container; do not use in production"
  python $BASE_DIR/manage.py collectstatic $COLLECT_STATIC_ARGS
  cd $THIS_DIR && npm run build && cd -
else
  docker exec -it thunor_app_1 python /thunor/manage.py collectstatic $COLLECT_STATIC_ARGS
  docker build -t thunor_webpack $THIS_DIR
  docker run --rm -v $BASE_DIR/_state:/_state -v $BASE_DIR/pyhts/static:/node-build/thunor thunor_webpack
  mv $BASE_DIR/_state/webpack-stats-processing.json $BASE_DIR/_state/webpack-stats.json
  echo "Restart the app server with 'docker-compose restart app' to reload changes"
fi

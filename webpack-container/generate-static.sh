#!/bin/bash

set -e

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "${THIS_DIR}" )"

mkdir -p $BASE_DIR/_state/webpack-bundles

if [ "$1" = "--no-container" ]; then
  echo "Processing staticfiles outside of container; do not use in production"
  cd $THIS_DIR && npm run build && cd -
  python $BASE_DIR/manage.py collectstatic --no-input --ignore pyhts
else
  docker build -t thunor_webpack $THIS_DIR
  docker run --rm -v $BASE_DIR/_state:/_state -v $BASE_DIR/pyhts/static/pyhts:/node-build/thunor thunor_webpack
  echo "Restart the app server with 'docker-compose restart app' to reload changes"
fi
cp thunor/502.html $BASE_DIR/_state/thunor-static/

#!/bin/bash

set -e

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "${THIS_DIR}" )"
DJANGO_STATIC_URL="$( grep ^DJANGO_STATIC_URL= $BASE_DIR/_conf/thunor.env | awk -F\= '{gsub(/"/,"",$2);print $2}' - )"
SITE_NAME="$( grep ^MAIN_SITE_NAME= $BASE_DIR/_conf/thunor.env | awk -F\= '{gsub(/"/,"",$2);print $2}' - )"
SITE_NAME=${SITE_NAME:-Thunor}

if [ "$1" = "--no-container" ]; then
  echo "Processing staticfiles outside of container; do not use in production"
  cd $THIS_DIR && npm run build && cd -
  python $BASE_DIR/manage.py collectstatic --no-input --ignore pyhts
else
  docker build -t thunor_webpack $THIS_DIR
  docker run --rm -v $BASE_DIR/_state/webpack-bundles:/_state/webpack-bundles -v $BASE_DIR/pyhts/static/pyhts:/node-build/thunor thunor_webpack
  docker-compose -f $BASE_DIR/docker-compose.base.yml run --rm -v $BASE_DIR/_state/webpack-bundles:/thunor/_state/webpack-bundles -v $BASE_DIR/_state/thunor-static:/thunor/_state/thunor-static --entrypoint python app manage.py collectstatic --no-input --ignore pyhts
  echo "Restart the app server with 'docker-compose restart app' to reload changes"
fi
cp $THIS_DIR/thunor/502.html $BASE_DIR/_state/thunor-static/
sed -i'.bak' 's|{{ SITE_NAME }}|'"${SITE_NAME}"'|g' $BASE_DIR/_state/thunor-static/502.html
sed -i'.bak' 's|{{ DJANGO_STATIC_URL }}|'"${DJANGO_STATIC_URL}"'|g' $BASE_DIR/_state/thunor-static/502.html

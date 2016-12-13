#!/bin/bash
THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$( dirname "${THIS_DIR}" )"
docker build -t thunor_webpack $THIS_DIR
docker run --rm -v $BASE_DIR/_state:/_state -v $BASE_DIR/pyhts/static:/node-build/thunor thunor_webpack
mv $BASE_DIR/_state/webpack-stats-processing.json $BASE_DIR/_state/webpack-stats.json
echo "Restart the app server with 'docker-compose restart app' to reload changes"

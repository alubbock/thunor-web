#!/bin/bash
set -e
if [ "$TRAVIS_BRANCH" != "master" ] || [ "$TRAVIS_PULL_REQUEST" != "false" ]; then
  echo "Not on branch master, or is a pull request. Skipping deploy."
  exit 0
fi

if [[ $DOCKER_PASSWORD ]]; then
  echo "$DOCKER_PASSWORD" | docker login -u alubbock --password-stdin
else
  echo "DOCKER_PASSWORD not set, skipping login"
fi

python thunorctl.py build || exit $?

if [[ $TRAVIS_TAG ]]; then
  echo "Release build: $TRAVIS_TAG"
  docker tag alubbock/thunorweb:dev alubbock/thunorweb:latest
  docker push alubbock/thunorweb:latest
  docker tag alubbock/thunorweb:dev "alubbock/thunorweb:$THUNORWEB_VERSION"
  docker push "alubbock/thunorweb:$THUNORWEB_VERSION"
else
  echo "Dev build"
  docker push alubbock/thunorweb:dev
fi

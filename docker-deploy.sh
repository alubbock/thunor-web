#!/bin/bash
set -ex
if [ "$TRAVIS_BRANCH" != "master" ] || [ "$TRAVIS_PULL_REQUEST" != "false" ]; then
  echo "Not on branch master, or is a pull request. Skipping deploy."
  exit 0
fi

if [[ $DOCKER_PASSWORD ]]; then
  echo "$DOCKER_PASSWORD" | docker login -u alubbock --password-stdin
else
  echo "DOCKER_PASSWORD not set, skipping login"
fi

# sudo b/c docker runs with elevated permissions, and creates otherwise unwriteable directories
sudo python thunorbld.py build || exit $?

# prepare SSH key for quickstart update
openssl aes-256-cbc -K $encrypted_15ee0f1bc0f8_key -iv $encrypted_15ee0f1bc0f8_iv \
  -in .thunor_web_quickstart_deploy_key.enc -out ./.thunor_web_quickstart_deploy_key -d
chmod 600 ./.thunor_web_quickstart_deploy_key
mv ./.thunor_web_quickstart_deploy_key ~/.ssh/id_rsa

# Get the quickstart repo
git clone git@github.com:/alubbock/thunor-web-quickstart
cd thunor-web-quickstart

if [[ $TRAVIS_TAG ]]; then
  echo "Release build: $TRAVIS_TAG"
  docker tag alubbock/thunorweb:dev alubbock/thunorweb:latest
  docker push alubbock/thunorweb:latest
  docker tag alubbock/thunorweb:dev "alubbock/thunorweb:$THUNORWEB_VERSION"
  docker push "alubbock/thunorweb:$THUNORWEB_VERSION"
  git checkout master
else
  echo "Dev build"
  docker push alubbock/thunorweb:dev
  git checkout dev
fi

# Copy files to quickstart repo and push
cp ../thunorctl.py .
cp ../docker-compose.services.yml .
rm -rf config-examples
cp -r ../config-examples .
sed -i 's/thunorweb:latest/thunorweb:dev/' config-examples/docker-compose.complete.yml
echo "$TRAVIS_COMMIT" > .release
git add -A
git status

if [[ $TRAVIS_TAG ]]; then
  git commit -m "Travis update: $TRAVIS_TAG"  
  git tag "$TRAVIS_TAG"
  git push --tags
else
  git commit -m "Travis update: $TRAVIS_COMMIT"
fi

git push

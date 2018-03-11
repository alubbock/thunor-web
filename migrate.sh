#!/bin/bash
if [ "$1" = "--dev" ]; then
  python manage.py migrate || exit $?
else
  docker-compose run --rm app python manage.py migrate || exit $1
fi

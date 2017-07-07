#!/bin/bash
docker-compose -f docker-compose.base.yml run app python manage.py migrate

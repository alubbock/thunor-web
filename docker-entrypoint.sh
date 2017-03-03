#!/bin/sh
python manage.py migrate
python manage.py collectstatic --no-input --ignore pyhts

# Start uWSGI process
uwsgi --socket :8000 --module web.wsgi --master --processes $UWSGI_PROCESSES --logto $UWSGI_LOGFILE --enable-threads --uid $THUNOR_USER --gid $THUNOR_GROUP

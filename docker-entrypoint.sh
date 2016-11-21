#!/bin/sh
python manage.py migrate

# Start Gunicorn processes
exec gunicorn web.wsgi:application \
    --name thunor \
    --bind 0.0.0.0:8000 \
    --workers $GUNICORN_WORKERS \
    --log-level=info \
    "$@"

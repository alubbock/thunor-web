FROM python:3.13-slim-bullseye AS thunorweb_base
LABEL org.opencontainers.image.authors="code@alexlubbock.com"
ENV PYTHONUNBUFFERED=1
ENV THUNOR_HOME=/thunor

RUN apt update && apt install -y libpq-dev gcc g++ libmagic1 libpcre3-dev media-types libhdf5-dev \
  && rm -rf /var/lib/apt/lists/*

RUN mkdir $THUNOR_HOME
WORKDIR $THUNOR_HOME

ADD requirements.txt $THUNOR_HOME
ADD thunorcore $THUNOR_HOME/thunorcore
RUN pip3 install --no-cache-dir -r requirements.txt
RUN dpkg --purge gcc libpcre3-dev
CMD ["uwsgi", "--master", "--socket", ":8000", "--module", "thunordjango.wsgi", "--uid", "www-data", "--gid", "www-data", "--enable-threads"]
ADD manage.py $THUNOR_HOME
ADD thunordjango $THUNOR_HOME/thunordjango
ADD thunorweb $THUNOR_HOME/thunorweb
ARG THUNORWEB_VERSION=unknown
RUN printf "def get_versions():\n    return {'version': '$THUNORWEB_VERSION'}\n" > $THUNOR_HOME/thunorweb/_version.py

FROM thunorweb_base AS thunorweb_static_build

COPY _state/deploy-test/_state/webpack-bundles $THUNOR_HOME/_state/webpack-bundles
RUN DJANGO_DEBUG=False DJANGO_SECRET_KEY= DJANGO_EMAIL_HOST= DJANGO_EMAIL_PORT= DJANGO_EMAIL_USER= \
    DJANGO_EMAIL_PASSWORD= POSTGRES_PASSWORD= python manage.py collectstatic --no-input

FROM thunorweb_base

COPY --from=thunorweb_static_build $THUNOR_HOME/_state/thunor-static $THUNOR_HOME/static

FROM python:3.14-slim-trixie AS thunorweb_base
LABEL org.opencontainers.image.authors="code@alexlubbock.com"
ENV PYTHONUNBUFFERED=1
ENV THUNOR_HOME=/thunor

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /bin/uv

RUN apt update && apt install -y libpq-dev gcc g++ libmagic1 libpcre2-dev media-types libhdf5-dev \
  && rm -rf /var/lib/apt/lists/*

RUN mkdir $THUNOR_HOME
WORKDIR $THUNOR_HOME

ADD pyproject.toml uv.lock $THUNOR_HOME/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
RUN dpkg --purge gcc g++ libhdf5-dev libpcre2-dev

ENV PATH="/thunor/.venv/bin:$PATH"

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', 8000)); s.close()"
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

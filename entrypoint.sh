#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"

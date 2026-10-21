#!/bin/sh
set -eu

mkdir -p /app/data /app/staticfiles /app/media
chown -R app:app /app/data /app/staticfiles /app/media

exec gosu app "$@"

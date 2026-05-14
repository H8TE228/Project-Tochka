#!/bin/sh
set -e

HOST="${DB_HOST:-localhost}"
PORT="${DB_PORT:-5432}"

echo "Waiting for database at ${HOST}:${PORT}..."
i=0
while [ "$i" -lt 60 ]; do
  if DB_HOST="$HOST" DB_PORT="$PORT" python -c "
import os, socket
h = os.environ['DB_HOST']
p = int(os.environ['DB_PORT'])
s = socket.socket()
s.settimeout(2)
s.connect((h, p))
s.close()
" 2>/dev/null; then
    echo "Database is accepting connections."
    break
  fi
  i=$((i + 1))
  sleep 1
done
if [ "$i" -eq 60 ]; then
  echo "Timeout: database not reachable."
  exit 1
fi

python manage.py migrate --noinput
exec "$@"

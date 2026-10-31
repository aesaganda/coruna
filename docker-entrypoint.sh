#!/bin/sh
set -e

# If arguments are passed with a flag, or no arguments are provided, default to main.py
if [ "$#" -eq 0 ] || [ "${1#-}" != "$1" ]; then
    exec python3 main.py "$@"
fi

exec "$@"

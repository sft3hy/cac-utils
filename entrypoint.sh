#!/bin/bash
set -e

# 1. Start D-Bus (Required by pcscd for authorization)
echo "Starting D-Bus..."
mkdir -p /var/run/dbus
dbus-daemon --system --fork

# 2. Start pcscd
echo "Starting pcscd..."
pcscd --foreground &

# Give services a moment to settle
sleep 2

# 3. Start the application
echo "Starting Application..."
exec gunicorn --bind 0.0.0.0:8000 server:app

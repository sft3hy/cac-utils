#!/bin/bash
set -e

# 1. Start D-Bus (Required by pcscd for authorization)
echo "Starting D-Bus..."
mkdir -p /var/run/dbus
mkdir -p /var/lib/dbus
if [ ! -f /var/lib/dbus/machine-id ]; then
    dbus-uuidgen > /var/lib/dbus/machine-id || echo "dbus-uuidgen failed, skipping"
fi
dbus-daemon --system --fork || echo "dbus-daemon already running or failed to start"

# 2. Start pcscd
echo "Starting pcscd..."
pcscd --foreground &

# Give services a moment to settle
echo "Waiting for services to settle..."
sleep 5

# 3. Start the application
echo "Starting Application with Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --access-logfile - --error-logfile - server:app

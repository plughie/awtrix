#!/usr/bin/env bash
# stop.sh — Stop the music visualizer and clear it from the Awtrix/Svitrix display.

LABEL="com.awtrix.music-visualizer"
DEVICE_IP="${AWTRIX_IP:-192.168.8.99}"
APP_NAME="visualizer"

# Stop the LaunchAgent
if launchctl list "$LABEL" &>/dev/null; then
    launchctl stop "$LABEL"
    echo "Stopped $LABEL"
else
    echo "$LABEL is not running"
fi

# Remove the custom app from the device and switch away
curl -s -X POST "http://${DEVICE_IP}/api/custom?name=${APP_NAME}" >/dev/null
curl -s -X POST "http://${DEVICE_IP}/api/switch" -H "Content-Type: application/json" -d '{"name":"Time"}' >/dev/null
echo "Cleared '${APP_NAME}' from device at ${DEVICE_IP}"

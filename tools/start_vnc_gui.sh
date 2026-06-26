#!/bin/sh
# Starts Xvfb + a VNC server + noVNC's websocket proxy, then launches the
# real GlyphViz GUI against that virtual display -- gives a real, mouse-
# interactive window reachable from a browser at http://localhost:6080/vnc_lite.html
# (see Dockerfile.linux). Manual Xvfb startup, not xvfb-run, since xvfb-run
# hangs as a container's PID 1 (its readiness handshake needs a SIGUSR1 that
# doesn't propagate reliably there).
set -e

Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
sleep 2

x11vnc -display :99 -forever -shared -nopw -quiet &
sleep 1

websockify -D --web=/usr/share/novnc/ 6080 localhost:5900

exec python3 main.py

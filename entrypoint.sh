#!/bin/bash
set -e

source /opt/ros/${ROS_DISTRO}/setup.bash
if [ -f /ws/install/setup.bash ]; then
  source /ws/install/setup.bash
fi

# Pi 5: libraries look for /dev/gpiochip4, but newer kernels expose the RP1
# 40-pin GPIO as gpiochip0 (gpiochip4 is only a host-side symlink that Docker
# does not pass through). docker-compose.yml already maps it; this is a
# fallback when running with --privileged.
if [ ! -e /dev/gpiochip4 ] && [ -e /dev/gpiochip0 ]; then
  ln -s /dev/gpiochip0 /dev/gpiochip4 2>/dev/null || true
fi

exec "$@"

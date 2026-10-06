# PiDog + ROS 2 Lyrical Luth container for Raspberry Pi 5 (arm64)
#
# Base: Ubuntu 26.04 / Python 3.14 (ros:lyrical-ros-base)
# Rule: prefer apt packages (python3-xxx) over pip. Many pip packages have no
#       Python 3.14 aarch64 wheel and fall back to a failing source build.
FROM ros:lyrical-ros-base

ENV DEBIAN_FRONTEND=noninteractive
# Pi 5 needs the lgpio backend for gpiozero (otherwise BadPinFactory)
ENV GPIOZERO_PIN_FACTORY=lgpio
ARG ROS_DISTRO=lyrical

# 1) Upgrade FIRST, then install.
#    The base image ships ROS core packages from its build date, while apt
#    installs the newest rosbridge etc. Mixing versions causes ABI errors like
#    "undefined symbol: has_buffer_fields_...". Upgrading keeps them in sync.
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
      python3-pip python3-dev git i2c-tools build-essential \
      # PiDog / robot-hat hardware dependencies
      python3-gpiozero python3-lgpio python3-smbus python3-smbus2 python3-spidev \
      python3-serial python3-pil python3-numpy \
      # Audio (robot_hat.music)
      python3-pyaudio portaudio19-dev libportaudio2 \
      python3-pygame libsdl2-mixer-2.0-0 \
      alsa-utils sox espeak \
      # ROS 2 packages
      ros-${ROS_DISTRO}-robot-state-publisher \
      ros-${ROS_DISTRO}-xacro \
      ros-${ROS_DISTRO}-rmw-zenoh-cpp \
      ros-${ROS_DISTRO}-foxglove-bridge \
      ros-${ROS_DISTRO}-rosbridge-suite \
      ros-${ROS_DISTRO}-teleop-twist-keyboard \
    && rm -rf /var/lib/apt/lists/*

# 2) SunFounder libraries + pure-python deps.
#    robot-hat's install.py edits HOST settings (config.txt, audio), so it is
#    run on the host only. Inside the container we install the python packages.
#    Check the Pi 5 compatible robot-hat branch (v2.0 at time of writing).
RUN pip3 install --break-system-packages \
      git+https://github.com/sunfounder/robot-hat.git@v2.0 \
      git+https://github.com/sunfounder/pidog.git \
      readchar

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
WORKDIR /ws
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]

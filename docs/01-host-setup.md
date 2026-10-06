# 1. 호스트 준비

## 1.1 OS와 ROS 2 배포판 선택

ROS 2 **Lyrical Luth**(2026년 5월 출시, 2031년 5월까지 지원하는 LTS)의 Tier 1 플랫폼은 Ubuntu 26.04(amd64/arm64)입니다. Pi 5에서 고를 수 있는 구성은 두 가지입니다.

| 구성 | 장점 | 단점 |
|---|---|---|
| A. Ubuntu 26.04 + ROS 2 네이티브 | ROS 쪽은 가장 깔끔 | robot-hat/pidog, I2S 스피커, CSI 카메라(libcamera)를 살리기 번거로움 |
| **B. Raspberry Pi OS 호스트 + ROS 2 Docker (추천)** | PiDog 하드웨어는 공식 환경 그대로 동작 | 컨테이너에 장치·권한을 넘겨주는 설정 필요 |

이 가이드는 **B 구성**을 따릅니다. PiDog처럼 벤더 드라이버 의존도가 높은 로봇은 B가 시행착오가 훨씬 적습니다.

## 1.2 I2C / SPI 활성화

```bash
sudo apt update && sudo apt full-upgrade -y
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo reboot

# 장치 확인
ls /dev/i2c-* /dev/spidev* /dev/gpiochip*
sudo apt install -y i2c-tools gpiod
i2cdetect -y 1     # Robot HAT MCU(보통 0x14)와 IMU 주소가 보여야 함
gpiodetect         # pinctrl-rp1 (54 lines) 인 칩 번호를 기록해 둘 것
```

`i2cdetect`에서 장치가 안 보이면 컨테이너에서도 당연히 안 보입니다. 배선과 전원을 먼저 확인하세요.

## 1.3 SunFounder 라이브러리 설치 (호스트)

ROS 없이 PiDog가 정상 동작하는지 먼저 확인합니다.

```bash
cd ~
git clone -b v2.0 https://github.com/sunfounder/robot-hat.git
cd robot-hat && sudo python3 install.py

cd ~
git clone https://github.com/sunfounder/pidog.git
cd pidog && sudo pip3 install . --break-system-packages

sudo bash ~/robot-hat/i2samp.sh   # 스피커(I2S)
```

> Pi 5는 GPIO가 RP1 칩으로 바뀌어서 구형 `RPi.GPIO`가 동작하지 않습니다. 반드시 Pi 5를 지원하는 robot-hat 2.x(lgpio 기반)를 쓰세요. 브랜치명은 설치 시점에 SunFounder 문서에서 확인하세요.

`~/pidog/examples/`의 기본 예제가 동작하면 다음으로 넘어갑니다.

### 서보 캘리브레이션

처음 조립했거나 서보를 교체했다면 받침대에 올린 상태로 보정합니다.

```bash
sudo python3 ~/robot-hat/example/servo_zeroing.py   # 조립 전 0점
cd ~/pidog/examples && sudo python3 0_calibration.py  # 정밀 보정
```

보정값은 호스트의 `pidog.conf`에 저장됩니다. **컨테이너에서도 이 파일을 보도록 마운트해야** 합니다([2단계](02-docker-ros2.md#24-docker-composeyml) 참고).

## 1.4 Docker 설치

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 그룹 권한은 이미 열린 SSH 세션에 반영되지 않음 → 재접속(가장 확실) 또는:
newgrp docker

docker run --rm hello-world
docker compose version
sudo systemctl enable docker   # 부팅 시 자동 시작
```

### 설치가 오래 멈춘 것처럼 보일 때

스크립트가 `apt-get -qq ... >/dev/null`로 실행돼 진행 상황이 안 보입니다. 정상이라면 1~5분, 느린 SD카드/네트워크면 10분 가까이 걸립니다. 15분 이상 멈춰 있다면 다른 터미널에서 확인합니다.

```bash
ps aux | grep -E "apt|dpkg|http|systemctl" | grep -v grep
sudo tail -f /var/log/apt/term.log
```

멈춘 게 확실하면 중단 후 진행 상황이 보이게 직접 설치합니다(저장소는 스크립트가 이미 등록해 둠).

```bash
sudo dpkg --configure -a && sudo apt-get -f install
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

> 사내망처럼 SSL 인스펙션이 있는 환경에서는 Docker 저장소·이미지 pull·pip 설치가 인증서 오류로 막힐 수 있습니다. 사내 루트 인증서를 `/usr/local/share/ca-certificates/`에 넣고 `sudo update-ca-certificates` 후 Docker를 재시작하거나, 테더링/집 네트워크에서 진행하세요.

## 1.5 ROS 2 이미지 동작 확인

```bash
docker pull ros:lyrical-ros-base

# 터미널 1
docker run --rm -it --network host --ipc host ros:lyrical-ros-base \
  ros2 topic pub /hello std_msgs/msg/String "{data: 'hi pidog'}"

# 터미널 2
docker run --rm -it --network host --ipc host ros:lyrical-ros-base \
  ros2 topic echo /hello
```

> **`--ipc host`를 빼먹으면 publish는 되는데 echo에 아무것도 안 나옵니다.** Fast DDS는 같은 호스트의 노드끼리 공유 메모리(SHM)로 통신하려 하는데, 컨테이너마다 `/dev/shm`이 격리돼 있어서 데이터가 전달되지 않습니다. 디스커버리는 UDP로 되므로 publisher는 정상처럼 보입니다.

---
다음: [2. ROS 2 컨테이너](02-docker-ros2.md)

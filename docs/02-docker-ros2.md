# 2. ROS 2 컨테이너 구성

## 2.1 디렉토리 구조

이 저장소를 Pi의 `~/pidog_ros`로 clone하면 그대로 이 구조가 됩니다.

```
~/pidog_ros/
├─ Dockerfile
├─ docker-compose.yml
├─ entrypoint.sh
└─ ws/                # 컨테이너의 /ws 로 마운트 (컨테이너를 지워도 코드는 남음)
   ├─ src/
   └─ web/
```

> Windows에서 파일을 편집해 복사하면 줄바꿈이 CRLF가 되어 `/bin/bash^M: bad interpreter` 에러가 납니다. `sed -i 's/\r$//' entrypoint.sh`로 변환하세요.

## 2.2 Dockerfile 핵심 포인트

전체 파일은 [`Dockerfile`](../Dockerfile)에 있습니다. 실제 구축 중 하나씩 부딪힌 문제들을 모두 반영한 최종본입니다.

**① `apt-get upgrade -y`를 설치 전에 먼저 실행**

베이스 이미지에는 빌드 시점의 ROS 코어가 들어 있고, `apt-get install`은 최신 rosbridge를 받아옵니다. 버전이 섞이면 `undefined symbol: has_buffer_fields_...` 같은 ABI 에러로 rosbridge가 바로 죽습니다.

**② 파이썬 의존성은 apt 패키지 우선**

컨테이너의 Python은 3.14라서 pip로 `pygame`, `pyaudio` 등을 설치하면 wheel이 없어 소스 빌드로 넘어가다 실패하기 쉽습니다. `python3-xxx` apt 패키지를 먼저 쓰고, apt에 없는 순수 파이썬 패키지(`readchar`)만 pip로 설치합니다.

| 모듈 | 누가 쓰나 | 패키지 |
|---|---|---|
| `gpiozero` | robot_hat.pin | `python3-gpiozero` (+ `GPIOZERO_PIN_FACTORY=lgpio`) |
| `lgpio` | gpiozero 백엔드 (Pi 5) | `python3-lgpio` |
| `smbus` | pidog.rgb_strip | `python3-smbus` (**`smbus2`와 다른 패키지**) |
| `smbus2`, `spidev` | robot_hat | `python3-smbus2`, `python3-spidev` |
| `pyaudio` | robot_hat.music | `python3-pyaudio` |
| `pygame` | robot_hat.music | `python3-pygame` |
| `readchar` | pidog.trot | pip `readchar` |

**③ robot-hat의 `install.py`는 컨테이너에서 실행하지 않음**

`install.py`는 `/boot/firmware/config.txt`나 오디오 설정 같은 **호스트** 작업을 포함합니다. 호스트에서 1단계에 이미 실행했으므로, 컨테이너에는 pip로 파이썬 패키지만 넣습니다.

**④ `onnxruntime`은 빼 둠**

Python 3.14 aarch64 wheel이 없으면 빌드 전체가 실패하므로, RL 정책 노드를 만들 때 따로 추가합니다.

## 2.3 entrypoint.sh

ROS 환경과 워크스페이스를 source하고, Pi 5의 `gpiochip4` 링크가 없으면 만들어 줍니다(compose 매핑의 예비책).

## 2.4 docker-compose.yml

[`docker-compose.yml`](../docker-compose.yml)에서 주의할 설정입니다.

| 설정 | 이유 |
|---|---|
| `network_mode: host` | ROS 디스커버리, rosbridge/웹 포트를 호스트에서 바로 사용 |
| `ipc: host` | 컨테이너 간 공유 메모리 통신 (빠지면 토픽 데이터가 안 옴) |
| `privileged: true` | 개발 단계 편의. 안정되면 `devices` + `group_add: [i2c, gpio, audio]`로 좁히기 |
| `/dev/gpiochip0:/dev/gpiochip4` | **Pi 5 필수.** 라이브러리는 `gpiochip4`를 찾는데 Docker는 호스트의 심볼릭 링크를 넘겨주지 않음 |
| `command: ros2 launch ...` | 컨테이너 시작 시 스택 자동 실행 |
| `stop_signal: SIGINT` | `docker compose stop` 시 Ctrl+C처럼 종료 → 로봇이 안전하게 멈춤 |
| `RMW_IMPLEMENTATION=rmw_zenoh_cpp` | Wi-Fi에서 DDS 멀티캐스트 디스커버리보다 안정적. 라우터는 `zenoh` 서비스 |

### GPIO 칩 확인

```bash
gpiodetect   # 호스트에서
```

`pinctrl-rp1 (54 lines)`가 `gpiochip0`이면 compose 그대로 쓰면 되고, `gpiochip4`로 나오면 두 줄의 **왼쪽**을 `/dev/gpiochip4`로 바꾸세요. compose에 존재하지 않는 장치를 적으면 컨테이너가 시작되지 않습니다.

### 캘리브레이션 파일 공유

호스트에서 `0_calibration.py`로 저장한 보정값을 컨테이너의 `Pidog()`가 못 보면 **호스트 예제에선 멀쩡한데 ROS로 돌리면 다리가 틀어지는** 증상이 생깁니다.

```bash
sudo find / -name "pidog.conf" -not -path "*/proc/*" 2>/dev/null       # 호스트
docker exec pidog find / -name "pidog.conf" -not -path "*/proc/*" 2>/dev/null  # 컨테이너가 읽는 경로
```

찾은 경로에 맞춰 compose의 주석 처리된 volume 줄을 활성화하세요. 예:

```yaml
      - /home/<사용자>/.config/pidog:/root/.config/pidog
```

## 2.5 빌드 및 하드웨어 접근 확인

처음에는 launch 패키지가 아직 빌드되지 않았으므로 셸로 들어가서 확인합니다.

```bash
cd ~/pidog_ros
docker compose build --pull
docker compose run --rm pidog bash

# 컨테이너 안에서
i2cdetect -y 1
python3 -c "from pidog import Pidog; d=Pidog(); print(d.accData, d.gyroData); d.close()"
```

> `Pidog()`를 생성하면 서보가 기본 자세로 움직입니다. 로봇을 받치거나 평평한 곳에 두세요.

IMU 값이 출력되면 컨테이너에서 하드웨어 제어가 되는 상태입니다. `ModuleNotFoundError`가 나면 누락 모듈을 한 번에 점검합니다.

```bash
# 호스트에서 (-it 가 아니라 -i: heredoc/파이프 입력 시 TTY 옵션을 쓰면 에러)
docker compose up -d zenoh
docker compose run --rm -T pidog python3 - < scripts/check_deps.py
```

`missing: []`이 나오면 됩니다. `vilib`(카메라) 같은 선택 모듈은 드라이버에 필요 없으니 무시해도 됩니다.

### `docker exec` 옵션 정리

| 옵션 | 용도 | 예 |
|---|---|---|
| `-it` | 직접 셸에서 대화형 작업 | `docker exec -it pidog bash` |
| `-i` | 파이프·heredoc으로 입력 전달 | `docker exec -i pidog python3 - < script.py` |
| 없음 | 입력 없는 단발 명령 | `docker exec pidog ros2 topic list` |
| `-d` | 백그라운드 실행 | `docker exec -d pidog python3 -m http.server ...` |

---
이전: [1. 호스트 준비](01-host-setup.md) · 다음: [3. 드라이버 노드](03-driver-node.md)

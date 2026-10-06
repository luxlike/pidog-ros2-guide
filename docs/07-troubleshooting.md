# 7. 트러블슈팅

실제 구축 과정에서 만난 에러를 순서대로 정리했습니다. 이 저장소의 Dockerfile/compose에는 아래 해결책이 모두 반영돼 있습니다.

## 빠른 참조

| 증상 | 원인 | 해결 |
|---|---|---|
| `get.docker.com` 설치가 오래 멈춤 | 진행 출력이 숨겨짐 / 네트워크·SSL 인스펙션 / apt lock | [1.4](01-host-setup.md#설치가-오래-멈춘-것처럼-보일-때) |
| `permission denied ... docker.sock` | docker 그룹이 현재 세션에 미반영 | 재로그인 또는 `newgrp docker` |
| `ros2 topic pub`은 되는데 `echo`가 조용함 | 컨테이너 간 `/dev/shm` 격리 | `--ipc host` / compose `ipc: host` |
| `No module named 'gpiozero'` | Dockerfile이 install.py 의존성을 안 깔음 | `python3-gpiozero` + `GPIOZERO_PIN_FACTORY=lgpio` |
| `No module named 'readchar'` | pidog.trot 의존성 | pip `readchar` |
| `No module named 'pyaudio'` | 컨테이너 재생성으로 수동 설치분 소실 | Dockerfile에 `python3-pyaudio` |
| `No module named 'smbus'` | `smbus2`만 설치됨 (다른 패키지) | `python3-smbus` |
| `undefined symbol: has_buffer_fields_...` | ROS 패키지 버전 불일치(ABI) | `apt-get upgrade -y` 먼저, `build --pull --no-cache` |
| `lgpio.error: 'can not open gpiochip'` | Pi 5 `gpiochip4` 링크가 컨테이너에 없음 | compose에 `/dev/gpiochip0:/dev/gpiochip4` |
| `cannot attach stdin to a TTY-enabled container` | heredoc/파이프에 `-it` 사용 | `-i`만 사용 |
| `/bin/bash^M: bad interpreter` | CRLF 줄바꿈 | `sed -i 's/\r$//' entrypoint.sh` |
| 웹은 열리는데 `WebSocket connection ... failed` | rosbridge 미실행 | [아래](#rosbridge-websocket-연결-실패) |
| 호스트 예제는 멀쩡한데 ROS로 돌리면 다리가 틀어짐 | 캘리브레이션 파일이 컨테이너에 안 보임 | [2.4](02-docker-ros2.md#캘리브레이션-파일-공유) |
| 서보 동작 중 I2C 에러/리셋 | 배터리 전압 강하 | 충전 확인, 드라이버 재시도 로직 |

## 의존성 누락은 한 번에 찾기

에러가 날 때마다 하나씩 고치지 말고, pidog/robot_hat이 import하는 모든 모듈을 한 번에 점검하세요.

```bash
docker exec -i pidog python3 - < scripts/check_deps.py
# missing: []  이면 OK
```

그리고 원칙: **컨테이너 안에서 apt/pip로 설치해 테스트 → 동작 확인되면 바로 Dockerfile에 반영.** 컨테이너 안 설치분은 `--force-recreate` 때 모두 사라집니다.

> 드라이버는 `respawn=True`라서 의존성 에러가 있는 동안 3초마다 같은 에러를 반복 출력합니다. 컨테이너 안에서 패키지를 설치하면 다음 재시작 때 자동으로 올라오므로, 재빌드 전에도 바로 확인할 수 있습니다.

## ROS 패키지 ABI 불일치

```
python3: symbol lookup error: /opt/ros/lyrical/lib/librosbridge_msgs__rosidl_typesupport_fastrtps_c.so:
undefined symbol: has_buffer_fields_builtin_interfaces__msg__Time
```

베이스 이미지의 구버전 코어와 apt로 받은 최신 rosbridge가 섞인 것입니다.

```bash
# 임시 (컨테이너 안)
apt-get update && apt-get upgrade -y

# 영구 (호스트) — Dockerfile은 이미 upgrade를 먼저 하도록 되어 있음
docker compose build --pull --no-cache
docker compose up -d --force-recreate
docker exec pidog bash -c "cd /ws && rm -rf build install log && colcon build --symlink-install"
```

컨테이너 안에서 ROS 패키지를 임시로 추가할 때도 항상 `apt-get update && apt-get upgrade -y`를 먼저 하세요.

## Pi 5 GPIO 칩 (`can not open gpiochip`)

최신 Pi 5 커널에서 40핀 GPIO(RP1)는 `gpiochip0`이고, 호스트에는 호환용 `gpiochip4 → gpiochip0` 심볼릭 링크가 있습니다. 하지만 라이브러리는 `gpiochip4`를 찾고, Docker는 이 링크를 컨테이너로 넘기지 않습니다.

```bash
gpiodetect                                  # 호스트: pinctrl-rp1 칩 확인
docker exec pidog ls -l /dev/gpiochip*      # 컨테이너: gpiochip4 유무

docker exec pidog python3 -c "
import lgpio
for c in (0, 4):
    try:
        h = lgpio.gpiochip_open(c); print(c, lgpio.gpio_get_chip_info(h)); lgpio.gpiochip_close(h)
    except Exception as e:
        print(c, 'ERROR', e)
"
```

compose에서 같은 호스트 장치를 두 이름으로 매핑하면 해결됩니다(이 저장소 기본값).

```yaml
    devices:
      - /dev/gpiochip0:/dev/gpiochip0
      - /dev/gpiochip0:/dev/gpiochip4
```

그래도 같은 에러면: lgpio는 작업 디렉토리에 `.lgd-nfy*` 파일을 만드는데, 쓰기 권한이 없어도 같은 메시지가 나옵니다(`docker exec pidog bash -c "cd /ws && touch .t && rm .t"`). 호스트에서 다른 GPIO 프로그램이 핀을 점유 중인지도 확인하세요(`ps aux | grep -E "pidog|python"`).

## rosbridge WebSocket 연결 실패

웹 페이지(8080)는 열리는데 `ws://<IP>:9090` 연결만 실패하는 경우.

```bash
sudo ss -ltnp | grep -E "9090|8080"      # 9090이 없으면 rosbridge가 안 떠 있음
docker compose ps
docker compose logs --tail 80 pidog

# rosbridge만 단독 실행해서 에러 확인
docker exec -it pidog bash -c \
  "source /ws/install/setup.bash && ros2 launch rosbridge_server rosbridge_websocket_launch.xml"
```

- rosbridge 로그 없이 `PiDog driver ready`만 있음 → compose `command`가 반영 안 됨 → `up -d --force-recreate pidog`
- `symbol lookup error` → 위의 ABI 불일치
- `package 'rosbridge_server' not found` → `apt-cache policy ros-lyrical-rosbridge-server`로 확인. 바이너리가 없으면 `ws/src`에 `rosbridge_suite`(ros2 브랜치)를 clone해 소스 빌드
- `No module named 'tornado'` 등 → `python3-tornado`처럼 apt로 설치
- 포트는 열려 있는데 안 되면 Pi 내부에서 핸드셰이크 확인:

```bash
curl -i -N --max-time 3 -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: SGVsbG8sIFBpRG9nIQ==" \
  http://localhost:9090      # 101 Switching Protocols 면 정상
```

정상이면 방화벽(`sudo ufw allow 9090/tcp`)이나 공유기 AP 격리를 확인하세요.

## 서보 과열·고장

서보가 뜨거워지고 일어서는 동작에서 힘을 못 쓰면 즉시 멈추세요. 자동 재시작 때문에 전원을 켜면 계속 일어서려 하므로 먼저 막습니다.

```bash
docker compose stop pidog
docker update --restart=no pidog
```

- **무부하 테스트**: 혼에서 서보를 떼고 `servo_zeroing.py` 실행. 안 움직이거나 소리만 나면 교체
- **케이블 교차 테스트**: 문제 서보와 정상 서보의 HAT 핀을 바꿔 꽂아, 증상이 서보를 따라가면 서보 고장, 핀을 따라가면 HAT 채널 문제
- **원인 제거 후 교체**: 0점 틀어짐, 혼 나사 풀림, 관절 걸림이 흔한 원인. 원인을 못 찾으면 새 서보도 같은 방식으로 망가짐
- 교체 후 `0_calibration.py`로 재보정하고, 받침대 위에서 먼저 테스트

---
이전: [6. Claude Code로 개발하기](06-dev-workflow.md) · 다음: [8. 로드맵](08-roadmap.md)

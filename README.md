# PiDog × ROS 2 연동 가이드

Raspberry Pi 5 기반 [SunFounder PiDog](https://github.com/sunfounder/pidog) 4족 로봇에 **ROS 2 Lyrical Luth**를 Docker로 올리고, 휴대폰(웹/iOS/Android)에서 조종하기까지의 전 과정을 정리한 가이드입니다. 실제로 구축하면서 겪은 에러와 해결 방법을 모두 반영했습니다.

> A step-by-step guide (in Korean) to running ROS 2 Lyrical in Docker on a Raspberry Pi 5 PiDog, with a unified driver node, rosbridge, and web / iOS / Android controllers.

## 무엇을 만드나

```
[휴대폰 브라우저 / iOS / Android 앱]
          │  WebSocket (9090)          HTTP (8080)
          ▼                                │
┌──────────────── pidog 컨테이너 (ROS 2 Lyrical) ────────────────┐
│  rosbridge_websocket ──/cmd_vel, /pidog/action──▶ pidog_driver │──▶ 서보 12개 / IMU
│  http.server (/ws/web)                                          │
└─────────────────────────────────────────────────────────────────┘
          ▲  rmw_zenoh
┌── pidog-zenoh 컨테이너 (zenoh 라우터) ──┐ ◀── 개발 PC / Foxglove
```

- **호스트**: Raspberry Pi OS 64-bit (SunFounder 라이브러리가 공식 지원하는 환경)
- **컨테이너**: `ros:lyrical-ros-base` (Ubuntu 26.04 / Python 3.14)
- **드라이버 노드 하나**가 `/cmd_vel`(보행), `/pidog/action`(내장 동작), `/joint_commands`(관절 직접 제어)를 받고 `/imu/data`, `/joint_states`를 발행합니다.
- `docker compose up -d` 한 번으로 드라이버 + rosbridge + 웹 컨트롤러가 함께 실행됩니다.

## 빠른 시작

호스트에서 PiDog가 이미 동작하는 상태(I2C/SPI 활성화, robot-hat 설치)라고 가정합니다. 처음이라면 [1. 호스트 준비](docs/01-host-setup.md)부터 보세요.

```bash
git clone <this-repo> ~/pidog_ros && cd ~/pidog_ros

# 1) Pi 5 GPIO 칩 이름 확인 → docker-compose.yml의 devices와 맞추기
gpiodetect            # pinctrl-rp1 이 gpiochip0 인지 확인

# 2) 이미지 빌드 (Pi 5에서 10분 안팎)
docker compose build --pull

# 3) 워크스페이스 최초 빌드
docker compose run --rm pidog bash -c "cd /ws && colcon build --symlink-install"

# 4) 실행 (드라이버 + rosbridge + 웹)
docker compose up -d
docker compose logs -f pidog   # "PiDog driver ready", "Rosbridge WebSocket server started on port 9090"
```

휴대폰을 같은 Wi-Fi에 연결하고 `http://<Pi IP>:8080` 에 접속하면 됩니다.

> ⚠️ 드라이버가 시작되면 로봇이 바로 일어섭니다. 평평한 바닥에 두고, 배터리가 충분한지 확인하세요.

## 가이드 목차

| 단계 | 문서 | 내용 |
|---|---|---|
| 1 | [호스트 준비](docs/01-host-setup.md) | OS·배포판 선택, I2C/SPI, robot-hat/pidog 설치, Docker 설치 |
| 2 | [ROS 2 컨테이너](docs/02-docker-ros2.md) | Dockerfile / compose / entrypoint, 하드웨어 접근 확인 |
| 3 | [드라이버 노드](docs/03-driver-node.md) | IMU 노드 → 통합 드라이버, 토픽 인터페이스, 테스트 명령 |
| 4 | [bringup + rosbridge](docs/04-bringup-rosbridge.md) | launch 파일, compose 자동 실행, 운영 명령 |
| 5 | [웹·모바일 컨트롤러](docs/05-web-mobile-clients.md) | rosbridge JSON 프로토콜, 웹 페이지, Swift / Kotlin 클라이언트 |
| 6 | [Claude Code로 개발하기](docs/06-dev-workflow.md) | Pi에서 Claude Code, CLAUDE.md, 권한 설정, git 워크플로 |
| 7 | [트러블슈팅](docs/07-troubleshooting.md) | 실제로 겪은 에러 모음과 해결법 |
| 8 | [로드맵](docs/08-roadmap.md) | 피지컬 AI 계층 구조, RL 정책 / FSM / VLA 연결 방향 |
| 9 | [색깔 공 추적 + 자연어 명령](docs/09-ball-tracking.md) | 카메라, HSV 공 검출, 고개·몸 추종, Claude/규칙 플래너 (VLA 1단계) |

## 저장소 구조

```
.
├─ Dockerfile              # ROS 2 Lyrical + PiDog 의존성 (검증된 최종본)
├─ docker-compose.yml      # zenoh 라우터 + pidog 서비스
├─ entrypoint.sh
├─ CLAUDE.md               # Claude Code용 프로젝트 설명 + 안전 규칙
├─ .claude/settings.json   # Claude Code 권한 설정
├─ ws/                     # colcon 워크스페이스 (컨테이너의 /ws)
│  ├─ src/pidog_driver/    # driver_node, imu_node
│  ├─ src/pidog_bringup/   # robot.launch.py, ball_follow.launch.py, config/*.yaml
│  ├─ src/pidog_perception/ # camera_node, ball_tracker_node (HSV 색 공 검출)
│  ├─ src/pidog_behavior/  # ball_follower_node, vla_planner_node (자연어 → 스킬)
│  └─ web/index.html       # 휴대폰 브라우저용 컨트롤러
├─ clients/                # iOS(Swift) / Android(Kotlin) rosbridge 클라이언트
├─ scripts/check_deps.py   # pidog/robot_hat 누락 모듈 일괄 점검
├─ scripts/camera_stream.py # 호스트용 picamera2 MJPEG 서버 (컨테이너 camera_node가 읽음)
└─ docs/                   # 단계별 가이드
```

## 꼭 기억할 규칙

1. **`Pidog()`는 한 프로세스에서만 생성합니다.** 두 노드가 같은 서보 컨트롤러를 잡으면 충돌합니다. 모든 하드웨어 접근은 `driver_node`를 거치세요.
2. **컨테이너 안에서 설치한 패키지는 컨테이너를 다시 만들면 사라집니다.** 테스트 후 바로 Dockerfile에 반영하세요.
3. **ROS 패키지를 apt로 추가할 때는 `apt-get upgrade -y`를 먼저** 해서 버전을 맞추세요.
4. rosbridge는 **인증이 없습니다.** 공용 네트워크에서는 `rosbridge:=false`로 실행하세요.

## 테스트 환경

| 항목 | 버전 |
|---|---|
| 보드 | Raspberry Pi 5 |
| 호스트 OS | Raspberry Pi OS 64-bit |
| ROS 2 | Lyrical Luth (2026년 5월 LTS, `ros:lyrical-ros-base`) |
| 컨테이너 Python | 3.14 |
| robot-hat | v2.0 브랜치 (Pi 5 / lgpio 지원) |

ROS 패키지 버전이나 SunFounder 브랜치명은 시간이 지나면 바뀔 수 있으니 설치 시점에 한 번 확인하세요. Lyrical에 아직 없는 서드파티 패키지가 필요하면 `jazzy`로 바꿔도 이후 과정은 같습니다.

## 라이선스

MIT. SunFounder `robot-hat`, `pidog` 라이브러리는 각 저장소의 라이선스를 따릅니다.

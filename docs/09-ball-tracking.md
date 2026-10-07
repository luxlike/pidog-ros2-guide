# 9. 색깔 공 추적 + 자연어 명령 (VLA 1단계)

"빨간 공 따라가", "파란 공 쳐다봐" 같은 명령을 알아듣고 카메라로 공을 찾아 고개로 추적하고, 걸어서 다가가는 기능입니다. [로드맵](08-roadmap.md)의 L3(인지)·L4(계획)를 가장 작은 형태로 연결합니다. 학습된 VLA 대신 **VLM/규칙 플래너 + 정해진 스킬** 구조로 먼저 파이프라인을 완성하고, 나중에 플래너만 학습형 모델로 바꿀 수 있게 인터페이스를 고정해 두었습니다.

## 구조

```
[호스트] scripts/camera_stream.py (picamera2 → MJPEG :8081)
              │ http://127.0.0.1:8081/stream.mjpg
┌─────────────┼──────────────── pidog 컨테이너 ─────────────────────────────────────┐
│  camera_node ──/camera/image_raw/compressed──▶ ball_tracker                     │
│                                                   │ /perception/balls (JSON)    │
│  /speech/text ─▶ vla_planner ──/ball_follower/target──▶ ball_follower           │
│  (웹·STT·CLI)     │  Claude tool use 또는                 │ /joint_commands (고개) │
│                   │  오프라인 규칙 파서                    │ /cmd_vel (회전·전진)      │
│                   └─/pidog/action, /speech/reply          ▼                     │
│                                                     pidog_driver ──▶ 서보        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

| 패키지 / 노드 | 역할 |
|---|---|
| `pidog_perception/camera_node` | 호스트 MJPEG 스트림(기본), USB 웹캠(v4l2), picamera2 중 하나를 읽어 JPEG 그대로 발행 |
| `pidog_perception/ball_tracker_node` | HSV 색 범위 + 원형도 검사로 색별 가장 큰 공 검출. 320px로 줄여 처리 |
| `pidog_behavior/ball_follower_node` | 목표 색 공을 고개 P제어로 중앙에 두고, 고개가 많이 돌면 몸 회전, 정면이면 전진, 충분히 크게 보이면 정지 |
| `pidog_behavior/vla_planner_node` | 텍스트 명령 + 현재 보이는 공 목록 → `follow_ball` / `do_action` / `stop` / `say` 스킬 호출 |

### 왜 카메라를 호스트에서 여나

Pi 5의 CSI 카메라는 libcamera + picamera2가 필요합니다. 둘 다 Raspberry Pi OS에는 들어 있지만 Ubuntu 기반 ROS 컨테이너에는 없고, 컨테이너 안에서 빌드하기도 까다롭습니다. 그래서 호스트가 카메라를 열고 MJPEG로 내보내며, 컨테이너는 `network_mode: host`로 `127.0.0.1:8081`에서 JPEG를 받아 **재인코딩 없이** 토픽으로 넘깁니다. USB 웹캠이라면 `source: v4l2`로 컨테이너에서 바로 열어도 됩니다(compose `devices`에 `/dev/video0` 추가).

## 설치

### 1) 이미지 다시 빌드

`Dockerfile`에 `python3-opencv`가 추가되었습니다.

```bash
cd ~/pidog_ros
docker compose build
docker compose up -d
docker exec pidog bash -c "cd /ws && colcon build --symlink-install"
docker compose restart pidog     # 드라이버 수정(고개 전용 명령) 반영
```

### 2) 호스트 카메라 스트림

```bash
# 호스트(Raspberry Pi OS)에서. vilib 예제 등 카메라를 쓰는 다른 프로그램은 먼저 종료
python3 scripts/camera_stream.py            # --vflip --hflip 으로 화면 방향 조정
curl -s -o /tmp/s.jpg http://127.0.0.1:8081/snapshot.jpg && file /tmp/s.jpg
```

부팅할 때 자동으로 켜려면 systemd 서비스로 등록합니다.

```ini
# /etc/systemd/system/pidog-camera.service
[Unit]
Description=PiDog camera MJPEG stream
After=network.target

[Service]
User=<사용자명>
ExecStart=/usr/bin/python3 /home/<사용자명>/pidog_ros/scripts/camera_stream.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now pidog-camera
```

### 3) (선택) Claude 플래너

`ANTHROPIC_API_KEY`가 없으면 오프라인 규칙 파서로 동작합니다. 키가 있으면 "가까운 공으로 가", "저기 있는 파란 거 쳐다봐"처럼 더 자유로운 문장도 처리합니다. SDK 없이 `urllib`만 쓰므로 추가 설치는 없습니다.

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/pidog_ros/.env    # .gitignore에 포함됨
docker compose up -d --force-recreate pidog
```

모델은 `config/ball.yaml`의 `vla_planner.model`(기본 `claude-haiku-4-5-20251001`, 응답 1초 안팎)로 바꿉니다. 네트워크 오류가 나면 자동으로 규칙 파서로 넘어가고, **"멈춰" 계열 명령은 항상 네트워크를 거치지 않고 즉시 처리**됩니다.

## 실행

드라이버(`robot.launch.py`)가 떠 있는 상태에서 추적 스택을 따로 띄웁니다.

```bash
docker exec -it pidog bash -c "source /ws/install/setup.bash && \
  ros2 launch pidog_bringup ball_follow.launch.py"
```

### 단계별 확인 (처음에는 몸체를 받침대에 올려 다리가 바닥에 닿지 않게)

```bash
docker exec -it pidog bash
source /ws/install/setup.bash

# 1. 카메라 → 15fps 정도 나오는지
ros2 topic hz /camera/image_raw/compressed

# 2. 검출 → 공을 카메라 앞에 두고 색·위치 확인
ros2 topic echo /perception/balls

# 3. 고개만 추적 (걷지 않음)
ros2 topic pub --once /ball_follower/target std_msgs/String "data: 'red:look'"
ros2 topic echo /ball_follower/status

# 4. 자연어 명령
ros2 topic pub --once /speech/text std_msgs/String "data: '빨간 공 따라가'"
ros2 topic echo /speech/reply

# 정지
ros2 topic pub --once /speech/text std_msgs/String "data: '멈춰'"
```

웹 컨트롤러(`http://<Pi IP>:8080`) 아래쪽에 **공 추적** 패널이 추가되었습니다. 색 버튼으로 추적을 시작하고, "고개로만 보기"를 체크하면 걷지 않으며, 텍스트 칸에 명령을 입력하면 `/speech/text`로 보냅니다. "카메라 보기"를 켜면 검출 결과(원·색 이름·목표 표시)가 그려진 디버그 영상을 5fps로 받습니다. 디버그 영상은 구독자가 있을 때만 인코딩하므로 평소 부하는 없습니다.

## 튜닝

### 고개 방향이 반대로 움직일 때

PiDog 헤드 각도 부호는 보정 상태에 따라 다를 수 있습니다. `red:look` 모드에서 공을 오른쪽으로 옮겼을 때 고개가 왼쪽으로 돌면 `yaw_sign: -1.0`, 위아래가 반대면 `pitch_sign: -1.0`으로 바꾸세요. `ball.yaml`은 `--symlink-install`로 설치되므로 노드만 다시 띄우면 됩니다.

### 색 범위

조명에 따라 HSV가 크게 달라집니다. 공이 안 잡히거나 엉뚱한 물체가 잡히면 `ball.yaml`의 `hsv.<색>`을 조정합니다(OpenCV 기준 H 0-179). 실제 공의 HSV 값은 스냅샷으로 확인합니다.

```bash
curl -s -o /tmp/s.jpg http://127.0.0.1:8081/snapshot.jpg
python3 -c "
import cv2; img = cv2.imread('/tmp/s.jpg'); h, w = img.shape[:2]
print(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[h//2-5:h//2+5, w//2-5:w//2+5].reshape(-1,3).mean(0))"
```

- 형광등 아래 주황/빨강이 섞이면 `orange` 하한 H를 올리고 `red` 상한을 낮춥니다.
- 바닥·벽 색이 잡히면 S 하한을 올립니다. 공 일부가 가려져 놓치면 `min_circularity`를 0.4까지 내립니다.

### 주요 파라미터 (`ball_follower`)

| 파라미터 | 기본 | 의미 |
|---|---|---|
| `walk` | true | false면 어떤 명령에도 걷지 않음(고개만) |
| `arrive_radius` | 0.16 | 공 반지름이 화면 폭의 16%가 되면 도착. 공 크기에 맞춰 조정 |
| `turn_yaw_threshold` | 25 | 고개가 이 각도 이상 돌면 몸을 회전 |
| `approach_yaw_max` | 15 | 고개가 이 각도 이내일 때만 전진 |
| `lost_timeout` / `search_timeout` | 1 / 8 s | 놓친 뒤 탐색 시작 / 포기까지 시간 |
| `max_follow_time` | 120 s | 한 번 추적의 최대 시간 |

## 안전 설계

- 목표를 지정하기 전에는 아무것도 움직이지 않습니다.
- 추종 노드는 이동할 때만 `/cmd_vel`을 보냅니다. 멈추면 드라이버 워치독(`cmd_timeout`)이 정지 후 일어서게 합니다.
- 플래너 출력은 `validate()`가 허용 목록(색 6개, 내장 동작 8개, stop/say)으로 걸러서 모델이 이상한 값을 내도 실행되지 않습니다.
- 드라이버 변경: `/joint_commands`에서 **다리 8개가 모두 NaN이면 보행 모드를 유지**합니다. 덕분에 걷는 중에도 고개 추적이 됩니다. 다리 값이 하나라도 있으면 기존처럼 관절 모드로 전환됩니다.
- 테이블 위에서는 쓰지 마세요. 초음파 근접 정지는 아직 없습니다(FSM 단계에서 추가 예정).

## 테스트

ROS 없이 로직만 검사하는 단위 테스트가 있습니다(합성 이미지 기반 검출 12개, 추종 제어·명령 파서 18개).

```bash
docker exec pidog bash -c "cd /ws && colcon test --packages-select pidog_perception pidog_behavior && colcon test-result --verbose"
```

## 다음 단계

- `/speech/text`에 whisper.cpp STT 노드, `/speech/reply`에 Piper TTS 노드 연결
- 초음파·터치 이벤트를 우선하는 FSM에서 `ball_follower`를 스킬 하나로 호출
- `ros2 bag record /camera/image_raw/compressed /speech/text /cmd_vel /joint_commands`로 시연 로그를 모아 VLA 파인튜닝 데이터로 사용 (플래너 인터페이스는 그대로 유지)

---
이전: [8. 로드맵](08-roadmap.md) · [README로](../README.md)

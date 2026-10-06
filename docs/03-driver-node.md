# 3. 드라이버 노드

## 3.1 먼저 IMU 노드로 하드웨어 확인 (선택)

`pidog_driver` 패키지에는 첫 번째 동작 확인용 `imu_node`가 들어 있습니다. 직접 패키지를 처음부터 만들어 보고 싶다면 다음과 같이 생성합니다.

```bash
cd /ws/src
ros2 pkg create pidog_driver --build-type ament_python \
  --dependencies rclpy sensor_msgs std_msgs --node-name imu_node
```

> `--node-name` 옵션이 만드는 파일은 `print('Hi from pidog_driver.')`만 있는 템플릿입니다. 실행했는데 "Hi from pidog_driver."만 나오면 코드를 아직 채우지 않은 것입니다.

```bash
cd /ws
colcon build --symlink-install
source install/setup.bash
ros2 run pidog_driver imu_node

# 다른 터미널: docker exec -it pidog bash
ros2 topic hz /imu/data           # 50Hz 근처
ros2 topic echo /imu/data --once
```

로봇 앞쪽을 들었을 때 어느 축 값이 변하는지 기록해 두면, 나중에 MuJoCo 모델의 IMU 좌표계와 맞출 때 유용합니다.

## 3.2 통합 드라이버 `driver_node`

[`driver_node.py`](../ws/src/pidog_driver/pidog_driver/driver_node.py)는 PiDog 하드웨어를 ROS 2에 연결하는 **유일한** 노드입니다.

> **`Pidog()`는 반드시 한 프로세스에서만 생성합니다.** 같은 I2C 서보 컨트롤러를 두 노드가 동시에 잡으면 충돌합니다. IMU 발행도 드라이버에 합쳐져 있으므로 `imu_node`와 동시에 실행하지 마세요.

### 토픽 인터페이스

| 방향 | 토픽 | 타입 | 설명 |
|---|---|---|---|
| 구독 | `/cmd_vel` | `geometry_msgs/Twist` | 전진·후진·회전 (부호/방향만 사용) |
| 구독 | `/pidog/action` | `std_msgs/String` | SunFounder 내장 동작 (`sit`, `stand`, `wag_tail`, `stop`...) |
| 구독 | `/joint_commands` | `std_msgs/Float64MultiArray` | 관절 12개 목표각, **도(degree)**, NaN = 현재 유지 |
| 발행 | `/imu/data` | `sensor_msgs/Imu` | SH3001 원시값 (50Hz) |
| 발행 | `/joint_states` | `sensor_msgs/JointState` | **명령된** 각도, **라디안** (50Hz) |

관절 순서:

```
0 lf_shoulder  1 lf_knee   2 rf_shoulder  3 rf_knee
4 lh_shoulder  5 lh_knee   6 rh_shoulder  7 rh_knee
8 head_yaw     9 head_roll 10 head_pitch  11 tail
```

### 파라미터 (`pidog_bringup/config/pidog.yaml`)

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `walk_speed` | 98 | 내장 보행 속도 (0~100) |
| `action_speed` | 80 | 내장 동작 속도 |
| `joint_speed` | 100 | 관절 직접 제어 속도 |
| `cmd_timeout` | 0.6 | `/cmd_vel`이 이 시간 동안 끊기면 정지 후 서기 (워치독) |

### 설계 포인트

- **워치독**: 앱이 꺼지거나 연결이 끊겨도 `cmd_timeout` 후 로봇이 멈춰 섭니다.
- **보행은 한 걸음씩**: PiDog 내장 보행은 속도 제어가 아니라 한 걸음 단위라서, `cmd_vel`의 부호와 방향만 사용하고 이전 걸음이 끝났을 때만 다음 걸음을 넣습니다. 속도 비례 보행은 이후 RL 정책이 맡습니다.
- **서보에 위치 피드백이 없음**: `/joint_states`는 실측값이 아니라 명령값입니다. RL 정책의 관측 공간을 설계할 때 고려하세요.
- **종료 처리**: `docker compose stop`은 시그널로 종료하므로 `KeyboardInterrupt`와 `ExternalShutdownException`을 모두 처리해 서보를 해제합니다.

## 3.3 빌드 및 실행

`setup.py`의 `entry_points`나 `package.xml`을 바꿨을 때만 다시 빌드합니다. 파이썬 코드만 바꿨다면 `--symlink-install` 덕분에 재실행만 하면 됩니다.

```bash
cd /ws
colcon build --symlink-install
source install/setup.bash
ros2 run pidog_driver driver_node    # 로봇이 바로 일어섭니다
```

`PiDog driver ready`가 뜨면 준비 완료입니다.

## 3.4 동작 테스트

다른 터미널에서 `docker exec -it pidog bash`로 접속합니다.

**내장 동작**

```bash
ros2 topic pub --once /pidog/action std_msgs/msg/String "{data: 'sit'}"
ros2 topic pub --once /pidog/action std_msgs/msg/String "{data: 'stand'}"
ros2 topic pub --once /pidog/action std_msgs/msg/String "{data: 'wag_tail'}"
ros2 topic pub --once /pidog/action std_msgs/msg/String "{data: 'stop'}"
```

`lie`, `stretch`, `push_up`, `shake_head`, `tilting_head`, `head_bark`, `doze_off` 등도 있습니다. 설치된 버전의 전체 목록:

```bash
grep -n "def " /usr/local/lib/python3.14/dist-packages/pidog/actions_dictionary.py
```

**보행**

```bash
# 10Hz로 발행하는 동안 걷고, Ctrl+C 후 워치독이 세움
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}}"
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist "{angular: {z: 0.5}}"
```

**관절 직접 제어** (NaN = 현재 각도 유지)

```bash
# 머리 왼쪽 30도
ros2 topic pub --once /joint_commands std_msgs/msg/Float64MultiArray \
  "{data: [.nan, .nan, .nan, .nan, .nan, .nan, .nan, .nan, 30.0, 0.0, 0.0, .nan]}"

# 머리 정면 + 꼬리 20도
ros2 topic pub --once /joint_commands std_msgs/msg/Float64MultiArray \
  "{data: [.nan, .nan, .nan, .nan, .nan, .nan, .nan, .nan, 0.0, 0.0, 0.0, 20.0]}"
```

다리 각도를 직접 넣을 때는 `ros2 topic echo /joint_states --once`로 현재 자세를 먼저 보고(라디안), 거기서 조금씩 바꿔 보세요.

**키보드 조종**

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

`i` 전진, `,` 후진, `j`/`l` 회전, `k` 정지. 걷다 멈추기를 반복하면 타임아웃을 늘립니다.

```bash
ros2 run pidog_driver driver_node --ros-args -p cmd_timeout:=1.0
```

## 3.5 현재 구조의 한계

`/joint_commands`는 PiDog 라이브러리의 `legs_move(immediately=True)`를 거칩니다. 라이브러리 내부 스레드가 목표각까지 보간하므로 수동 제어에는 부드럽고 안전하지만, **50Hz로 매 스텝 목표각을 덮어쓰는 RL 정책에는 지연이 생깁니다.** 정책을 올릴 때는 robot-hat 서보에 직접 쓰는 저수준 모드를 따로 추가하는 것이 좋습니다.

---
이전: [2. ROS 2 컨테이너](02-docker-ros2.md) · 다음: [4. bringup + rosbridge](04-bringup-rosbridge.md)

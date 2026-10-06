# 4. bringup 패키지와 rosbridge

드라이버, rosbridge(WebSocket 9090), 웹 페이지 서버(8080)를 launch 파일 하나로 묶고, `docker compose up` 시 자동 실행되게 합니다.

```
[iOS/Android 앱, 웹 페이지] --WebSocket(9090)--> [rosbridge_websocket] --/cmd_vel--> [pidog_driver] --> 서보
                                         (pidog 컨테이너 안에서 launch로 함께 실행)
```

## 4.1 패키지 구성

```
ws/src/pidog_bringup/
├─ launch/robot.launch.py
├─ config/pidog.yaml
├─ package.xml          # exec_depend: launch, launch_ros, pidog_driver, rosbridge_server
└─ setup.py             # launch/, config/ 를 share 디렉토리에 설치
```

직접 만든다면:

```bash
cd /ws/src
ros2 pkg create pidog_bringup --build-type ament_python
mkdir -p pidog_bringup/launch pidog_bringup/config
```

`setup.py`의 `data_files`에 launch/config를 등록하지 않으면 `ros2 launch`가 파일을 찾지 못합니다.

## 4.2 launch 인자

| 인자 | 기본값 | 설명 |
|---|---|---|
| `rosbridge` | `true` | rosbridge WebSocket 서버 실행 |
| `rosbridge_port` | `9090` | rosbridge 포트 |
| `web` | `true` | `/ws/web`을 8080 포트로 서빙 |

드라이버는 `respawn=True`(3초 후 재시작)로 실행됩니다.

```bash
ros2 launch pidog_bringup robot.launch.py                   # 전체
ros2 launch pidog_bringup robot.launch.py rosbridge:=false  # 공용 네트워크
```

## 4.3 먼저 수동으로 테스트

따로 실행 중인 `driver_node`가 있으면 먼저 종료하세요(`Pidog()` 중복 금지).

```bash
cd /ws
colcon build --symlink-install
source install/setup.bash
ros2 launch pidog_bringup robot.launch.py
```

`PiDog driver ready`와 `Rosbridge WebSocket server started on port 9090`이 함께 보이면 성공입니다.

## 4.4 compose 자동 실행

이 저장소의 `docker-compose.yml`에는 이미 다음이 들어 있습니다.

```yaml
    command: ros2 launch pidog_bringup robot.launch.py
    stop_signal: SIGINT        # Ctrl+C와 동일하게 종료
    stop_grace_period: 15s
    restart: unless-stopped
```

```bash
cd ~/pidog_ros
docker compose up -d --force-recreate
docker compose logs -f pidog
```

이제 Pi를 재부팅하면 zenoh 라우터, 드라이버, rosbridge, 웹 서버가 자동으로 올라옵니다.

## 4.5 운영 명령 모음

```bash
docker compose up -d                       # 시작
docker compose logs --tail 50 pidog        # 로그
docker compose restart pidog               # 파이썬 코드 수정 후 재시작
docker compose stop pidog                  # 정지 (서보 해제 후 종료)
docker exec -it pidog bash                 # ros2 CLI 사용

# 새 패키지 추가 / setup.py 변경 시
docker exec pidog bash -c "cd /ws && colcon build --symlink-install"
docker compose restart pidog
```

| 변경한 것 | 필요한 조치 |
|---|---|
| 웹 페이지(`ws/web/*`) | 브라우저 새로고침 |
| 파이썬 노드 코드, launch 파일 | `docker compose restart pidog` |
| 새 노드/패키지, `setup.py`, `package.xml` | `colcon build` 후 재시작 |
| `docker-compose.yml` | `docker compose up -d --force-recreate pidog` |
| `Dockerfile`, `entrypoint.sh` | `docker compose build` 후 `up -d --force-recreate` |

### 빌드가 깨져서 컨테이너가 재시작을 반복할 때

```bash
docker compose stop pidog
docker compose run --rm pidog bash     # launch 없이 셸만 띄워서 수정·빌드
```

### 로봇 수리 중 자동 실행 막기

서보 고장 등으로 수리할 때는 전원을 켜자마자 일어서려고 하지 않도록 자동 재시작을 끕니다.

```bash
docker compose stop pidog
docker update --restart=no pidog
# 수리 후
docker update --restart=unless-stopped pidog
```

## 4.6 보안

rosbridge는 **인증이 없어서** 같은 네트워크의 누구나 로봇을 조종하고 모든 토픽을 볼 수 있습니다. 집 네트워크 개발용으로만 쓰고, 공용 Wi-Fi에서는 `rosbridge:=false`로 실행하세요. 외부 접속이 필요하면 WSS(TLS)나 VPN을 앞단에 두는 구성을 고려하세요.

---
이전: [3. 드라이버 노드](03-driver-node.md) · 다음: [5. 웹·모바일 컨트롤러](05-web-mobile-clients.md)

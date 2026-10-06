# 5. 웹·모바일 컨트롤러

별도의 ROS 라이브러리 없이 각 플랫폼의 기본 WebSocket만으로 rosbridge에 붙습니다.

## 5.1 rosbridge 프로토콜 (필요한 건 두 가지뿐)

```json
{"op": "advertise", "topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist"}

{"op": "publish", "topic": "/cmd_vel",
 "msg": {"linear": {"x": 0.2, "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}}
```

연결 직후 `advertise`로 토픽 타입을 알리고, 이후 `publish`를 반복합니다. 내장 동작은 `/pidog/action`(`std_msgs/msg/String`, `{"data": "sit"}`)으로 보냅니다.

### 조이스틱 패턴 (모든 클라이언트 공통)

- 누르고 있는 동안 **10Hz로 반복 발행**
- 손을 떼면 **0 명령을 한 번** 발행
- 앱이 백그라운드로 가거나 연결이 끊겨도 드라이버 워치독(0.6초)이 로봇을 세움

## 5.2 웹 컨트롤러 (가장 빠른 검증)

[`ws/web/index.html`](../ws/web/index.html)은 외부 라이브러리 없는 단일 파일 컨트롤러입니다. launch의 `web:=true`(기본값)로 8080 포트에서 자동 서빙됩니다.

수동으로 띄우려면:

```bash
docker exec -d pidog python3 -m http.server 8080 -d /ws/web
```

확인:

```bash
sudo ss -ltnp | grep -E "8080|9090"   # 둘 다 보여야 함
hostname -I                           # Pi IP
```

휴대폰을 같은 Wi-Fi에 연결하고 `http://<Pi IP>:8080`에 접속합니다. 상단에 "연결됨: ws://<Pi IP>:9090"이 표시되면 방향 버튼과 동작 버튼으로 조종할 수 있습니다. 다른 터미널에서 `docker exec pidog ros2 topic echo /cmd_vel`을 띄워 두면 메시지 흐름도 볼 수 있습니다.

> 공유기에서 Pi IP를 DHCP 예약으로 고정해 두면 주소가 바뀌지 않아 편합니다.

> `docker exec -d`로 띄운 웹 서버는 컨테이너가 재시작되면 함께 종료됩니다. launch에 포함된 방식(기본값)을 쓰면 신경 쓸 필요가 없습니다.

### 웹 페이지는 열리는데 WebSocket 연결이 실패할 때

[트러블슈팅 → rosbridge](07-troubleshooting.md#rosbridge-websocket-연결-실패)를 참고하세요. 대부분 rosbridge가 실제로 떠 있지 않거나(ABI 에러) launch가 실행되지 않은 경우입니다.

## 5.3 iOS (Swift)

[`clients/ios/RosBridgeClient.swift`](../clients/ios/RosBridgeClient.swift) — `URLSessionWebSocketTask` 기반.

```swift
let client = RosBridgeClient()
client.connect(host: "192.168.0.29")
client.startMoving(vx: 0.2, wz: 0)   // 버튼 누름
client.stopMoving()                  // 버튼 뗌
client.action("sit")
```

**Info.plist 필수 항목** (없으면 연결이 조용히 실패):

- `NSAppTransportSecurity` → `NSAllowsLocalNetworking = YES`
- `NSLocalNetworkUsageDescription` = "PiDog 로봇 제어를 위해 로컬 네트워크에 접속합니다"

## 5.4 Android (Kotlin)

[`clients/android/RosBridgeClient.kt`](../clients/android/RosBridgeClient.kt) — OkHttp + 코루틴 기반.

```kotlin
val client = RosBridgeClient("192.168.0.29")
client.startMoving(0.2, 0.0)
client.stopMoving()
client.action("sit")
client.close()
```

**AndroidManifest.xml 필수 항목**:

- `<uses-permission android:name="android.permission.INTERNET" />`
- `<application android:usesCleartextTraffic="true">` (또는 network security config로 Pi IP 대역만 허용)

Android 9 이상은 기본적으로 암호화 없는 `ws://`를 막습니다.

## 5.5 음성 명령을 붙일 때 참고 (iOS)

웹 페이지에 Web Speech API로 음성 명령을 붙이면 HTTPS가 필요하고(로컬 인증서는 mkcert 등으로 생성), **iPhone에서는 Safari에서만** 동작합니다. iOS의 Chrome 등 서드파티 브라우저는 음성 인식 API를 쓸 수 없고, Safari도 설정에서 받아쓰기(Dictation)가 켜져 있어야 합니다.

## 5.6 다음 단계 아이디어

- `/imu/data`, `/joint_states`를 `subscribe`해서 앱에 자세·상태 표시
- 카메라 영상 스트리밍 (Pi 5 카메라는 컨테이너에서 libcamera를 쓰기 어려우므로, 호스트에서 Picamera2로 MJPEG 스트림을 띄우고 컨테이너는 `localhost`로 읽는 구성이 간단)
- 시각화는 `foxglove_bridge`(8765)를 띄우고 Foxglove 앱에서 `ws://<Pi IP>:8765`로 접속

---
이전: [4. bringup + rosbridge](04-bringup-rosbridge.md) · 다음: [6. Claude Code로 개발하기](06-dev-workflow.md)

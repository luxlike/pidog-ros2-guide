// Minimal rosbridge client for PiDog (iOS, URLSessionWebSocketTask, no extra libraries)
//
// Info.plist requirements for plain ws:// on the local network:
//   NSAppTransportSecurity > NSAllowsLocalNetworking = YES
//   NSLocalNetworkUsageDescription = "PiDog 로봇 제어를 위해 로컬 네트워크에 접속합니다"
// Without these the connection fails silently.

import Foundation

final class RosBridgeClient {
    private var task: URLSessionWebSocketTask?
    private var repeatTimer: Timer?
    private var current = (vx: 0.0, wz: 0.0)

    func connect(host: String, port: Int = 9090) {
        guard let url = URL(string: "ws://\(host):\(port)") else { return }
        task = URLSession.shared.webSocketTask(with: url)
        task?.resume()
        send(["op": "advertise", "topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist"])
        send(["op": "advertise", "topic": "/pidog/action", "type": "std_msgs/msg/String"])
    }

    /// Call while the joystick is held: publishes at 10 Hz
    func startMoving(vx: Double, wz: Double) {
        current = (vx, wz)
        publishCmdVel()
        repeatTimer?.invalidate()
        repeatTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            self?.publishCmdVel()
        }
    }

    /// Call when the joystick is released
    func stopMoving() {
        repeatTimer?.invalidate()
        current = (0, 0)
        publishCmdVel()
    }

    /// Built-in action: "sit", "stand", "lie", "wag_tail", "stop", ...
    func action(_ name: String) {
        send(["op": "publish", "topic": "/pidog/action", "msg": ["data": name]])
    }

    func disconnect() {
        stopMoving()
        task?.cancel(with: .normalClosure, reason: nil)
    }

    private func publishCmdVel() {
        send(["op": "publish", "topic": "/cmd_vel", "msg": [
            "linear": ["x": current.vx, "y": 0, "z": 0],
            "angular": ["x": 0, "y": 0, "z": current.wz]]])
    }

    private func send(_ obj: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              let text = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(text)) { error in
            if let error { print("rosbridge send error: \(error)") }
        }
    }
}

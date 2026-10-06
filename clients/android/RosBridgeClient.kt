// Minimal rosbridge client for PiDog (Android, Kotlin + OkHttp + coroutines)
//
// AndroidManifest.xml requirements:
//   <uses-permission android:name="android.permission.INTERNET" />
//   <application android:usesCleartextTraffic="true" ...>
//     (or a network security config allowing only the Pi's IP range)
// Android 9+ blocks plain ws:// by default.

import kotlinx.coroutines.*
import okhttp3.*
import org.json.JSONObject

class RosBridgeClient(host: String, port: Int = 9090) {
    private val ws: WebSocket = OkHttpClient().newWebSocket(
        Request.Builder().url("ws://$host:$port").build(),
        object : WebSocketListener() {
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                android.util.Log.e("RosBridge", "connection failed", t)
            }
        })
    private val scope = CoroutineScope(Dispatchers.IO)
    private var repeatJob: Job? = null

    init {
        // OkHttp queues messages sent before the socket opens
        ws.send("""{"op":"advertise","topic":"/cmd_vel","type":"geometry_msgs/msg/Twist"}""")
        ws.send("""{"op":"advertise","topic":"/pidog/action","type":"std_msgs/msg/String"}""")
    }

    /** Call while the joystick is held: publishes at 10 Hz */
    fun startMoving(vx: Double, wz: Double) {
        repeatJob?.cancel()
        repeatJob = scope.launch {
            while (isActive) {
                publishCmdVel(vx, wz)
                delay(100)
            }
        }
    }

    /** Call when the joystick is released */
    fun stopMoving() {
        repeatJob?.cancel()
        publishCmdVel(0.0, 0.0)
    }

    /** Built-in action: "sit", "stand", "lie", "wag_tail", "stop", ... */
    fun action(name: String) {
        val msg = JSONObject().put("data", name)
        ws.send(JSONObject().put("op", "publish").put("topic", "/pidog/action").put("msg", msg).toString())
    }

    private fun publishCmdVel(vx: Double, wz: Double) {
        val msg = JSONObject()
            .put("linear", JSONObject().put("x", vx).put("y", 0).put("z", 0))
            .put("angular", JSONObject().put("x", 0).put("y", 0).put("z", wz))
        ws.send(JSONObject().put("op", "publish").put("topic", "/cmd_vel").put("msg", msg).toString())
    }

    fun close() {
        stopMoving()
        scope.cancel()
        ws.close(1000, null)
    }
}

"""Stage-1 "VLA" planner: text command + what the camera sees -> skill calls.

Subscribes
  /speech/text            std_msgs/String  command text (from STT node, web UI, or ros2 topic pub)
  /perception/balls       std_msgs/String  JSON from ball_tracker_node (scene context)
  /ball_follower/status   std_msgs/String  forwarded as spoken feedback (found / arrived / gave_up)

Publishes
  /ball_follower/target   std_msgs/String  "<color>" | "<color>:look" | "stop"
  /pidog/action           std_msgs/String  built-in actions
  /speech/reply           std_msgs/String  text for TTS / UI

Backend (parameter `backend`)
  auto   (default) Claude if ANTHROPIC_API_KEY is set, otherwise offline rules
  claude Claude Messages API tool use; falls back to rules on network/API errors
  rules  offline keyword parser only
"""
import json
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from pidog_behavior.command_parser import COLOR_KO, ClaudePlanner, RuleParser

STATUS_REPLIES = {
    'found': '{c} 공 찾았다!',
    'arrived': '{c} 공 앞에 도착했어요.',
    'gave_up': '{c} 공을 못 찾겠어요.',
}


class VlaPlanner(Node):
    def __init__(self):
        super().__init__('vla_planner')
        self.declare_parameter('backend', 'auto')
        self.declare_parameter('model', 'claude-haiku-4-5-20251001')
        self.declare_parameter('timeout', 15.0)
        self.declare_parameter('scene_max_age', 1.0)

        self.rules = RuleParser()
        self.claude = None
        backend = self.get_parameter('backend').value
        if backend in ('auto', 'claude'):
            try:
                self.claude = ClaudePlanner(self.get_parameter('model').value,
                                            timeout=float(self.get_parameter('timeout').value))
            except RuntimeError as e:
                lvl = self.get_logger().warn if backend == 'claude' else self.get_logger().info
                lvl(f'Claude backend disabled ({e}) -> offline rules')

        self.balls, self.balls_time = [], 0.0
        self.busy = threading.Lock()

        self.create_subscription(String, 'speech/text', self.on_text, 10)
        self.create_subscription(String, 'perception/balls', self.on_balls, 10)
        self.create_subscription(String, 'ball_follower/status', self.on_status, 10)
        self.target_pub = self.create_publisher(String, 'ball_follower/target', 10)
        self.action_pub = self.create_publisher(String, 'pidog/action', 10)
        self.reply_pub = self.create_publisher(String, 'speech/reply', 10)
        self.get_logger().info(
            f'vla_planner ready (backend={"claude:" + self.claude.model if self.claude else "rules"})')

    # ---------- inputs ----------
    def on_balls(self, msg):
        try:
            self.balls = json.loads(msg.data).get('balls', [])
            self.balls_time = time.monotonic()
        except json.JSONDecodeError:
            pass

    def on_status(self, msg):
        try:
            st = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        tpl = STATUS_REPLIES.get(st.get('event'))
        if tpl and st.get('target'):
            self.reply(tpl.format(c=COLOR_KO.get(st['target'], st['target'])))

    def on_text(self, msg):
        text = msg.data.strip()
        if not text:
            return
        # Stop must never wait for the network
        quick = self.rules.parse(text)
        if quick and quick[0]['name'] == 'stop':
            self.execute(quick, text, 'rules')
            return
        if not self.busy.acquire(blocking=False):
            self.reply('잠깐만요, 이전 명령을 처리 중이에요.')
            return
        threading.Thread(target=self.plan, args=(text,), daemon=True).start()

    # ---------- planning (worker thread) ----------
    def plan(self, text):
        try:
            fresh = time.monotonic() - self.balls_time < float(
                self.get_parameter('scene_max_age').value)
            scene = list(self.balls) if fresh else []
            calls, src = None, 'rules'
            if self.claude:
                t0 = time.monotonic()
                try:
                    calls = self.claude.parse(text, scene)
                    src = f'claude {time.monotonic() - t0:.1f}s'
                except Exception as e:  # noqa: BLE001
                    self.get_logger().warn(f'Claude failed: {e} -> rules')
            if not calls:
                calls = self.rules.parse(text, scene)
            self.execute(calls, text, src)
        finally:
            self.busy.release()

    def execute(self, calls, text, src):
        self.get_logger().info(f'"{text}" -> {json.dumps(calls, ensure_ascii=False)} ({src})')
        for c in calls:
            name, inp = c['name'], c['input']
            if name == 'follow_ball':
                tgt = inp['color'] + (':look' if inp.get('mode') == 'look' else '')
                self.target_pub.publish(String(data=tgt))
            elif name == 'do_action':
                if inp['action'] != 'wag_tail':
                    self.target_pub.publish(String(data='stop'))
                self.action_pub.publish(String(data=inp['action']))
            elif name == 'stop':
                self.target_pub.publish(String(data='stop'))
                self.action_pub.publish(String(data='stop'))
            if inp.get('reply'):
                self.reply(inp['reply'])

    def reply(self, text):
        self.get_logger().info(f'reply: {text}')
        self.reply_pub.publish(String(data=text))


def main():
    from rclpy.executors import ExternalShutdownException

    rclpy.init()
    node = VlaPlanner()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

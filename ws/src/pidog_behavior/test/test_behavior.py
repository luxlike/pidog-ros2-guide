"""Tests for the follow controller and the offline command parser (no ROS needed).

    cd ws/src/pidog_behavior && python3 -m pytest test -q
"""
from pidog_behavior.command_parser import RuleParser, describe_scene, validate
from pidog_behavior.follow_controller import (
    APPROACHING, ARRIVED, IDLE, LOST, SEARCHING, TRACKING, FollowController, FollowParams)

DT = 0.1


def run(ctrl, t, ball, n=1):
    cmd = None
    for _ in range(n):
        t += DT
        cmd = ctrl.update(t, ball)
    return t, cmd


# ---------------- follow controller ----------------
def test_idle_until_started():
    c = FollowController()
    cmd = c.update(0.0, (0.5, 0, 0.05))
    assert cmd.state == IDLE and not cmd.moving


def test_centered_far_ball_approaches():
    c = FollowController()
    c.start(0.0)
    _, cmd = run(c, 0.0, (0.0, 0.0, 0.05))
    assert cmd.state == APPROACHING and cmd.moving and cmd.vx > 0 and cmd.wz == 0


def test_ball_on_right_head_turns_right_then_body_turns_right():
    c = FollowController()
    c.start(0.0)
    t, cmd = run(c, 0.0, (0.8, 0.0, 0.05))
    assert cmd.head_yaw < 0                      # yaw_sign=+1: negative yaw = look right
    t, cmd = run(c, t, (0.8, 0.0, 0.05), n=10)   # ball stays at the right edge
    assert cmd.head_yaw <= -25 and cmd.moving and cmd.wz < 0 and cmd.vx == 0


def test_ball_above_head_pitches_up():
    c = FollowController(FollowParams(walk=False))
    c.start(0.0)
    _, cmd = run(c, 0.0, (0.0, -0.6, 0.05), n=3)
    assert cmd.head_pitch > 0 and not cmd.moving


def test_look_mode_never_walks():
    c = FollowController(FollowParams(walk=False))
    c.start(0.0)
    _, cmd = run(c, 0.0, (0.9, 0.0, 0.01), n=30)
    assert not cmd.moving and cmd.head_yaw == -60   # clamped at yaw_limit


def test_arrive_and_resume_hysteresis():
    c = FollowController()
    c.start(0.0)
    t, cmd = run(c, 0.0, (0.0, 0.0, 0.2), n=3)
    assert cmd.state == ARRIVED and not cmd.moving
    t, cmd = run(c, t, (0.0, 0.0, 0.14), n=5)       # slightly smaller: still arrived
    assert cmd.state == ARRIVED
    t, cmd = run(c, t, (0.0, 0.0, 0.05), n=8)       # ball moved away -> approach again
    assert cmd.state == APPROACHING and cmd.vx > 0


def test_arrived_event_once():
    c = FollowController()
    c.start(0.0)
    events = []
    t = 0.0
    for _ in range(10):
        t += DT
        events += c.update(t, (0.0, 0.0, 0.3)).events
    assert events.count('arrived') == 1


def test_short_dropout_holds_then_search_then_lost():
    p = FollowParams(lost_timeout=1.0, search_timeout=2.0)
    c = FollowController(p)
    c.start(0.0)
    t, cmd = run(c, 0.0, (-0.8, 0.0, 0.05), n=10)   # ball on the left
    assert cmd.head_yaw > 0
    t, cmd = run(c, t, None, n=5)                    # 0.5 s dropout
    assert cmd.state in (TRACKING, APPROACHING) and not cmd.moving
    t, cmd = run(c, t, None, n=6)                    # > lost_timeout
    assert cmd.state == SEARCHING and cmd.wz > 0     # turns toward last seen side (left)
    t, cmd = run(c, t, None, n=25)
    assert cmd.state == LOST and not cmd.moving


def test_found_while_searching():
    c = FollowController()
    c.start(0.0)
    t, cmd = run(c, 0.0, None, n=3)
    assert cmd.state == SEARCHING
    t, cmd = run(c, t, (0.0, 0.0, 0.05))
    assert 'found' in cmd.events


# ---------------- rule parser ----------------
P = RuleParser()
BALLS = [{'color': 'blue', 'x': 0.5, 'y': 0.0, 'radius': 0.1},
         {'color': 'red', 'x': -0.4, 'y': 0.1, 'radius': 0.04}]


def one(text, balls=None):
    calls = P.parse(text, balls)
    assert len(calls) == 1
    return calls[0]


def test_follow_color_ko():
    c = one('빨간 공 따라가')
    assert c['name'] == 'follow_ball' and c['input'] == {**c['input'], 'color': 'red', 'mode': 'follow'}


def test_look_mode_ko():
    c = one('노란 공 쳐다봐')
    assert c['input']['color'] == 'yellow' and c['input']['mode'] == 'look'


def test_nearest_ball_uses_scene():
    c = one('가까운 공으로 가', BALLS)
    assert c['name'] == 'follow_ball' and c['input']['color'] == 'blue'


def test_ball_without_color_and_nothing_seen_asks():
    assert one('공 따라가')['name'] == 'say'


def test_stop_wins():
    assert one('파란 공 그만 따라가')['name'] == 'stop'


def test_actions():
    assert one('앉아')['input']['action'] == 'sit'
    assert one('꼬리 흔들어')['input']['action'] == 'wag_tail'
    assert one('엎드려')['input']['action'] == 'lie'


def test_english():
    c = one('follow the green ball')
    assert c['input']['color'] == 'green' and c['input']['mode'] == 'follow'


def test_validate_drops_unknown():
    out = validate([{'name': 'follow_ball', 'input': {'color': 'pink', 'mode': 'follow'}},
                    {'name': 'do_action', 'input': {'action': 'jump_off_table'}},
                    {'name': 'rm_rf', 'input': {}},
                    {'name': 'stop', 'input': {'reply': 'ok'}}])
    assert [c['name'] for c in out] == ['stop']


def test_describe_scene():
    s = describe_scene(BALLS)
    assert 'blue' in s and '오른쪽' in s and '왼쪽' in s
    assert describe_scene([]) == '카메라에 보이는 공 없음'

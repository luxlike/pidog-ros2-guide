"""Ball-follow controller (pure python, no ROS -> unit-testable).

Head first, body second:
  1. The head (yaw/pitch) keeps the ball centered in the image (P control on pixel error).
  2. If the head has to look far to the side, the body turns toward it.
  3. Once the head is roughly straight, the body walks forward until the ball looks
     big enough (radius = fraction of image width) -> ARRIVED.
  4. Ball not seen for `lost_timeout` -> SEARCHING (head back to center, turn toward
     where it was last seen). After `search_timeout` -> LOST (stop).

Sign conventions (check on the real robot with the body lifted):
  image x: -1 left .. +1 right,  image y: -1 top .. +1 bottom
  head yaw:   +  = look left  (yaw_sign = +1). Flip with yaw_sign = -1.
  head pitch: +  = look up    (pitch_sign = +1). Flip with pitch_sign = -1.
  body wz:    +  = turn left  (same as the driver: wz > 0 -> turn_left)
"""
from dataclasses import dataclass, field

IDLE, TRACKING, APPROACHING, ARRIVED, SEARCHING, LOST = (
    'idle', 'tracking', 'approaching', 'arrived', 'searching', 'lost')


@dataclass
class FollowParams:
    walk: bool = True               # False = head tracking only (no walking)
    kp_yaw: float = 8.0             # deg per tick at full-frame error
    kp_pitch: float = 6.0
    deadband: float = 0.06          # ignore small image errors
    yaw_limit: float = 60.0
    pitch_min: float = -25.0
    pitch_max: float = 20.0
    yaw_sign: float = 1.0
    pitch_sign: float = 1.0
    turn_yaw_threshold: float = 25.0   # head yaw beyond this -> body turns
    approach_yaw_max: float = 15.0     # walk forward only when head is this straight
    arrive_radius: float = 0.16        # ball radius / image width considered "close"
    resume_ratio: float = 0.75         # leave ARRIVED when radius < arrive_radius * ratio
    smoothing: float = 0.5             # EMA weight of the new measurement
    lost_timeout: float = 1.0
    search_timeout: float = 8.0
    search_turn: bool = True
    vx: float = 0.2
    wz: float = 0.5


@dataclass
class FollowCommand:
    state: str
    head_yaw: float
    head_pitch: float
    vx: float = 0.0
    wz: float = 0.0
    moving: bool = False            # True -> publish cmd_vel this tick
    events: list = field(default_factory=list)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class FollowController:
    def __init__(self, params: FollowParams | None = None):
        self.p = params or FollowParams()
        self.reset()

    def reset(self):
        self.state = IDLE
        self.yaw = 0.0
        self.pitch = 0.0
        self.est = None            # smoothed (x, y, radius)
        self.last_seen = None
        self.last_side = 0.0       # +1 last seen on the left (positive yaw), -1 right
        self.search_start = None

    def start(self, now):
        self.reset()
        self.state = SEARCHING
        self.search_start = now
        self.last_seen = now

    def stop(self):
        self.state = IDLE
        self.est = None

    def update(self, now, ball):
        """ball: (x, y, radius) of the target, or None if not visible this tick."""
        p = self.p
        events = []
        if self.state in (IDLE, LOST):
            return FollowCommand(self.state, self.yaw, self.pitch)

        if ball is not None:
            if self.est is None:
                self.est = ball
            else:
                a = p.smoothing
                self.est = tuple(a * n + (1 - a) * o for n, o in zip(ball, self.est))
            self.last_seen = now
            if self.state in (SEARCHING,):
                events.append('found')
                self.state = TRACKING
            x, y, r = self.est

            # 1) head P control
            if abs(x) > p.deadband:
                self.yaw -= p.kp_yaw * x * p.yaw_sign
            if abs(y) > p.deadband:
                self.pitch -= p.kp_pitch * y * p.pitch_sign
            self.yaw = _clamp(self.yaw, -p.yaw_limit, p.yaw_limit)
            self.pitch = _clamp(self.pitch, p.pitch_min, p.pitch_max)
            if abs(self.yaw) > 1.0:
                self.last_side = 1.0 if self.yaw > 0 else -1.0

            if not p.walk:
                return FollowCommand(self.state, self.yaw, self.pitch, events=events)

            # 2) arrival with hysteresis
            if self.state == ARRIVED:
                if r < p.arrive_radius * p.resume_ratio:
                    self.state = TRACKING
                else:
                    return FollowCommand(ARRIVED, self.yaw, self.pitch, events=events)
            elif r >= p.arrive_radius and abs(self.yaw) <= p.approach_yaw_max:
                self.state = ARRIVED
                events.append('arrived')
                return FollowCommand(ARRIVED, self.yaw, self.pitch, events=events)

            # 3) body: turn first, then approach
            if abs(self.yaw) > p.turn_yaw_threshold:
                self.state = TRACKING
                wz = p.wz if self.yaw > 0 else -p.wz
                return FollowCommand(self.state, self.yaw, self.pitch, wz=wz, moving=True,
                                     events=events)
            if abs(self.yaw) <= p.approach_yaw_max:
                self.state = APPROACHING
                return FollowCommand(self.state, self.yaw, self.pitch, vx=p.vx, moving=True,
                                     events=events)
            self.state = TRACKING   # in between: let the head settle, body waits
            return FollowCommand(self.state, self.yaw, self.pitch, events=events)

        # ---- ball not visible this tick ----
        if self.state != SEARCHING and now - self.last_seen < p.lost_timeout:
            # brief dropout: hold head, stop body (driver watchdog stands it up if long)
            return FollowCommand(self.state, self.yaw, self.pitch, events=events)

        if self.state != SEARCHING:
            self.state = SEARCHING
            self.search_start = now
            self.est = None
            events.append('lost_sight')

        if now - self.search_start > p.search_timeout:
            self.state = LOST
            events.append('gave_up')
            return FollowCommand(LOST, self.yaw, self.pitch, events=events)

        # head back toward center, slightly down to see the floor
        self.yaw *= 0.8
        self.pitch += (-10.0 - self.pitch) * 0.2
        if p.walk and p.search_turn:
            side = self.last_side or 1.0
            return FollowCommand(SEARCHING, self.yaw, self.pitch, wz=p.wz * side, moving=True,
                                 events=events)
        return FollowCommand(SEARCHING, self.yaw, self.pitch, events=events)

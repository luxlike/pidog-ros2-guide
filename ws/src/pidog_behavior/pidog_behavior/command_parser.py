"""Natural-language command -> skill calls.

Two backends with the same output format (list of {"name": ..., "input": {...}}):
  RuleParser    offline keyword matching (Korean/English), no network
  ClaudePlanner Claude Messages API with tool use (urllib only, no SDK dependency)
"""
import json
import os
import urllib.error
import urllib.request

COLOR_ALIASES = {
    'red': ['빨간', '빨강', '붉은', 'red'],
    'orange': ['주황', '오렌지', 'orange'],
    'yellow': ['노란', '노랑', 'yellow'],
    'green': ['초록', '녹색', '연두', 'green'],
    'blue': ['파란', '파랑', '푸른', 'blue'],
    'purple': ['보라', '자주', 'purple'],
}
COLOR_KO = {'red': '빨간', 'orange': '주황', 'yellow': '노란', 'green': '초록',
            'blue': '파란', 'purple': '보라'}

# Built-in SunFounder actions exposed to the planner (subset known to be safe on a table/floor)
ACTIONS = ['stand', 'sit', 'lie', 'wag_tail', 'stretch', 'shake_head', 'head_bark', 'push_up']

STOP_WORDS = ['멈춰', '정지', '그만', '스톱', '멈추', 'stop', 'halt']
LOOK_WORDS = ['쳐다', '바라봐', '봐줘', '봐', '주시', 'look', 'watch']
FOLLOW_WORDS = ['따라', '추적', '쫓아', '가져', '가봐', '가', '찾아', '다가', 'follow', 'chase',
                'go', 'find', 'track']
ANY_BALL_WORDS = ['가까운', '아무', '큰 공', 'nearest', 'closest', 'any']
ACTION_WORDS = [
    ('wag_tail', ['꼬리', 'wag']),
    ('sit', ['앉아', '앉', 'sit']),
    ('lie', ['엎드려', '누워', '엎드', 'lie', 'down']),
    ('stand', ['일어나', '일어서', '서', 'stand', 'up']),
    ('stretch', ['기지개', 'stretch']),
    ('shake_head', ['고개', 'shake']),
    ('head_bark', ['짖어', '멍', 'bark']),
    ('push_up', ['팔굽', '푸시업', 'push']),
]


def find_color(text):
    t = text.lower()
    hits = [(t.find(w), c) for c, ws in COLOR_ALIASES.items() for w in ws if w in t]
    return min(hits)[1] if hits else None


def describe_scene(balls):
    """balls: list of dicts from /perception/balls -> short text for the planner."""
    if not balls:
        return '카메라에 보이는 공 없음'
    parts = []
    for b in balls:
        side = '왼쪽' if b['x'] < -0.3 else '오른쪽' if b['x'] > 0.3 else '가운데'
        dist = '가까이' if b['radius'] > 0.12 else '중간' if b['radius'] > 0.05 else '멀리'
        parts.append(f"{b['color']}({COLOR_KO.get(b['color'], b['color'])}) 공: {side}, {dist}, "
                     f"radius={b['radius']}")
    return '; '.join(parts)


class RuleParser:
    name = 'rules'

    def parse(self, text, balls=None):
        t = text.lower().strip()
        balls = balls or []
        if any(w in t for w in STOP_WORDS):
            return [{'name': 'stop', 'input': {'reply': '멈출게요.'}}]

        color = find_color(t)
        mentions_ball = color or '공' in t or 'ball' in t
        if mentions_ball:
            if not color and any(w in t for w in ANY_BALL_WORDS) and balls:
                color = max(balls, key=lambda b: b['radius'])['color']
            if not color:
                if balls:
                    color = max(balls, key=lambda b: b['radius'])['color']
                else:
                    return [{'name': 'say', 'input': {'reply': '어떤 색 공인지 알려주세요.'}}]
            mode = 'look' if any(w in t for w in LOOK_WORDS) and \
                not any(w in t for w in ('따라', '가', 'follow', 'go')) else 'follow'
            verb = '쳐다볼게요' if mode == 'look' else '따라갈게요'
            return [{'name': 'follow_ball',
                     'input': {'color': color, 'mode': mode,
                               'reply': f'{COLOR_KO.get(color, color)} 공을 {verb}.'}}]

        for action, words in ACTION_WORDS:
            if any(w in t for w in words):
                return [{'name': 'do_action', 'input': {'action': action, 'reply': '네!'}}]
        return [{'name': 'say', 'input': {'reply': '무슨 말인지 잘 모르겠어요.'}}]


TOOLS = [
    {
        'name': 'follow_ball',
        'description': ('카메라로 특정 색의 공을 찾아 고개로 추적하고(mode=look), '
                        '필요하면 걸어서 다가간다(mode=follow). 공이 안 보이면 제자리에서 돌며 찾는다.'),
        'input_schema': {
            'type': 'object',
            'properties': {
                'color': {'type': 'string', 'enum': list(COLOR_ALIASES.keys())},
                'mode': {'type': 'string', 'enum': ['follow', 'look'],
                         'description': 'follow=다가가기, look=제자리에서 고개로만 바라보기'},
                'reply': {'type': 'string', 'description': '사용자에게 할 짧은 한국어 대답'},
            },
            'required': ['color', 'mode', 'reply'],
        },
    },
    {
        'name': 'do_action',
        'description': '내장 동작 실행. 진행 중인 공 추적은 먼저 멈춘다(wag_tail 제외).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'enum': ACTIONS},
                'reply': {'type': 'string'},
            },
            'required': ['action', 'reply'],
        },
    },
    {
        'name': 'stop',
        'description': '모든 이동과 추적을 멈춘다.',
        'input_schema': {'type': 'object', 'properties': {'reply': {'type': 'string'}},
                         'required': ['reply']},
    },
    {
        'name': 'say',
        'description': '동작 없이 대답만 한다 (명령이 모호하거나 수행 불가할 때 되묻기).',
        'input_schema': {'type': 'object', 'properties': {'reply': {'type': 'string'}},
                         'required': ['reply']},
    },
]

SYSTEM_PROMPT = """너는 4족 로봇 강아지 PiDog의 행동 플래너다.
사용자의 한국어/영어 명령과 현재 카메라 인식 결과를 보고 반드시 도구 하나 이상을 호출한다.
- 공 색이 명시되지 않았는데 "가까운 공", "저 공"처럼 말하면 인식 결과에서 가장 큰(가까운) 공을 고른다.
- 요청한 색의 공이 지금 안 보여도 follow_ball을 호출한다(로봇이 돌면서 찾는다). 단 reply에 찾아보겠다고 말한다.
- 위험하거나 할 수 없는 요청(계단, 높은 곳, 사람에게 달려들기 등)은 say로 거절한다.
- reply는 강아지답게 짧고 친근하게 한 문장."""


class ClaudePlanner:
    name = 'claude'
    URL = 'https://api.anthropic.com/v1/messages'

    def __init__(self, model, api_key=None, timeout=15.0):
        self.model = model
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY', '')
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError('ANTHROPIC_API_KEY is not set')

    def parse(self, text, balls=None):
        body = {
            'model': self.model,
            'max_tokens': 400,
            'system': SYSTEM_PROMPT,
            'tools': TOOLS,
            'tool_choice': {'type': 'any'},
            'messages': [{'role': 'user', 'content':
                          f'[카메라 인식] {describe_scene(balls or [])}\n[명령] {text}'}],
        }
        req = urllib.request.Request(
            self.URL, data=json.dumps(body).encode(), method='POST',
            headers={'content-type': 'application/json', 'x-api-key': self.api_key,
                     'anthropic-version': '2023-06-01'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'HTTP {e.code}: {e.read()[:300]!r}') from e
        calls = [{'name': c['name'], 'input': c.get('input', {})}
                 for c in data.get('content', []) if c.get('type') == 'tool_use']
        return validate(calls)


def validate(calls):
    """Drop anything outside the allowed skill set (never trust model output blindly)."""
    ok = []
    for c in calls:
        name, inp = c.get('name'), dict(c.get('input') or {})
        if name == 'follow_ball':
            if inp.get('color') not in COLOR_ALIASES:
                continue
            if inp.get('mode') not in ('follow', 'look'):
                inp['mode'] = 'follow'
        elif name == 'do_action':
            if inp.get('action') not in ACTIONS:
                continue
        elif name not in ('stop', 'say'):
            continue
        inp['reply'] = str(inp.get('reply', ''))[:200]
        ok.append({'name': name, 'input': inp})
    return ok

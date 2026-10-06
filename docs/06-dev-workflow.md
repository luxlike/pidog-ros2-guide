# 6. Claude Code로 개발하기

채팅에서 코드를 받아 붙여넣고, 에러를 복사해 다시 묻는 왕복 대신 **Pi 호스트에 Claude Code를 설치**하면 파일 수정 → `colcon build` → 재시작 → 로그 확인 → 수정을 한 번에 반복할 수 있습니다.

## 6.1 어디서 무엇을 할까

| 방식 | 적합한 작업 |
|---|---|
| 채팅 + 복사·붙여넣기 | 설계 논의, 개념 정리 |
| **Pi에서 Claude Code** | 드라이버, ROS 노드, 하드웨어 디버깅 (실물에서 돌려봐야 아는 코드) |
| PC/맥에서 Claude Code + git | MuJoCo 학습, 정책 export (계산량이 큰 작업) |

## 6.2 설치 (컨테이너가 아니라 호스트에)

호스트에 설치해야 `docker compose`, `docker exec`로 컨테이너를 다룰 수 있습니다. Claude Code는 유료 플랜(Pro/Max/Team/Enterprise) 또는 Console 계정이 필요합니다.

```bash
curl -fsSL https://claude.ai/install.sh | bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
claude --version
```

npm으로 설치한다면 `sudo` 없이 사용자 경로에 설치하세요(자동 업데이트와 권한 충돌 방지).

```bash
mkdir -p ~/.npm-global && npm config set prefix ~/.npm-global
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
npm install -g @anthropic-ai/claude-code --loglevel http
```

### npm 설치가 멈춘 것처럼 오래 걸릴 때

- **IPv6 우선 문제 (Pi에서 흔함)**: `export NODE_OPTIONS=--dns-result-order=ipv4first` 후 재시도
- **SSL 인스펙션 사내망**: `npm config set cafile <사내루트.crt>`, `export NODE_EXTRA_CA_CERTS=<사내루트.crt>`
- **Node가 너무 오래됨**: `node -v`가 18 미만이면 NodeSource로 최신 LTS 설치
- npm과 네이티브 설치기를 동시에 깔면 `PATH` 순서에 따라 다른 버전이 실행되니 하나만 남기세요.

화면 없는 Pi에서 `claude`를 실행하면 로그인 URL이 출력됩니다. 맥 브라우저에서 열어 인증하면 됩니다.

## 6.3 CLAUDE.md와 권한 설정

이 저장소에는 이미 두 파일이 들어 있습니다.

- [`CLAUDE.md`](../CLAUDE.md): 환경 설명, 자주 쓰는 명령, **안전 규칙**("`Pidog()` 중복 생성 금지", "로봇을 움직이는 명령은 실행 전 사용자 확인")
- [`.claude/settings.json`](../.claude/settings.json): 로그·상태·빌드 같은 안전한 명령은 자동 허용, `docker exec`/재시작은 확인 요청, 위험한 명령은 차단

`docker exec`를 전부 `ask`로 둔 이유는 `ros2 topic pub`처럼 로봇을 움직이는 명령이 대부분 이 형태로 실행되기 때문입니다. 익숙해지면 `ros2 topic list`/`echo` 같은 읽기 전용 명령만 `allow`에 추가하세요.

## 6.4 사용 흐름

```bash
ssh pi@<PI_IP>
tmux new -s claude      # SSH가 끊겨도 유지 (재접속: tmux attach -t claude)
cd ~/pidog_ros
claude
```

```
> driver_node에 초음파 센서 거리값을 sensor_msgs/Range로 /range 토픽에 발행하는 기능 추가해줘.
  빌드하고 로그에 에러 없는지 확인한 다음, 재시작은 나한테 물어보고 해.
```

VS Code를 쓴다면 Remote-SSH로 Pi에 접속해 원격 터미널에서 `claude`를 실행하면 변경 내용을 에디터로 같이 볼 수 있습니다.

## 6.5 MuJoCo 학습과 연결

```
pidog-project/           # git 저장소 하나
├─ sim/                  # MuJoCo 모델, 학습 코드 → PC에서 작업
├─ policies/             # export된 .onnx (git LFS 권장)
└─ pidog_ros/            # 이 저장소 → Pi에서 작업
```

PC에서 학습·export·push → Pi의 Claude Code에게 "최신 정책 pull 받아서 locomotion 노드로 띄워봐". 양쪽 `CLAUDE.md`에 **관측·액션 공간(관절 순서, 단위, 제어 주기)**을 동일하게 적어 두면 sim/real 사이에서 관절 순서가 어긋나는 실수를 줄일 수 있습니다.

---
이전: [5. 웹·모바일 컨트롤러](05-web-mobile-clients.md) · 다음: [7. 트러블슈팅](07-troubleshooting.md)

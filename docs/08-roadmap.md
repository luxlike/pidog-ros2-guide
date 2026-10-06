# 8. 로드맵: 피지컬 AI 계층 구조

이 저장소는 L0(드라이버)까지를 다룹니다. 그 위로 쌓아 갈 구조는 다음과 같습니다. 위로 갈수록 느리고 똑똑하게, 아래로 갈수록 빠르고 단순하게 둡니다.

| 계층 | 주기 / 위치 | 역할 |
|---|---|---|
| **L0 드라이버** ✅ | 50Hz, Pi | 서보/IMU/센서 I/O, 안전 워치독 |
| L1 보행 정책 | 50Hz, Pi | MuJoCo에서 학습한 정책을 ONNX로 export → onnxruntime 추론. 입력 `/cmd_vel`, IMU, 이전 액션 → 출력 `/joint_commands` |
| L2 행동 FSM | ~10Hz, Pi | 터치·소리·얼굴 인식 이벤트로 상태 전이, `/cmd_vel`·action 호출로 동작. 커지면 py_trees 등 비헤이비어 트리 |
| L3 인지·음성 | Pi 또는 가속기 | 얼굴 검출/인식, 로컬 STT(whisper.cpp), TTS(Piper). 비전 부하가 크면 Hailo AI HAT+ |
| L4 추론·계획 | PC / 클라우드 | LLM/VLM이 자연어 명령을 L2의 action/service 호출로 변환 (tool calling). Zenoh로 연결 |

**네트워크가 끊겨도 L0~L2만으로 안전하게 동작**하도록 설계하는 것이 핵심입니다. VLA/VLM 출력도 반드시 FSM을 거치게 하고, 센서 기반 안전 체크(초음파 근접, 터치, 기울기)가 우선하도록 합니다.

## 권장 워크스페이스 구조

sim과 real이 **같은 토픽 인터페이스**를 공유하도록 설계합니다.

```
ws/src/
├─ pidog_interfaces/     # 커스텀 msg/srv (TouchState, SoundDirection ...)
├─ pidog_description/    # URDF/xacro (MuJoCo MJCF와 치수·관절 한계 일치)
├─ pidog_driver/         # ✅ 실물 하드웨어
├─ pidog_bringup/        # ✅ launch (sim:=true/false)
├─ pidog_sim_mujoco/     # MuJoCo를 돌리며 driver와 같은 토픽 발행 (+ /clock)
├─ pidog_locomotion/     # RL 정책(ONNX) 추론
├─ pidog_behavior/       # FSM 행동 에이전트
├─ pidog_perception/     # 얼굴 인식, 카메라
└─ pidog_voice/          # STT/TTS, 사운드 방향
```

## sim-to-real 주의점

- PiDog 서보는 **위치 피드백이 없습니다.** 관측에 관절 위치를 넣었다면 학습 때 "이전 액션"으로 대체하거나 서보 지연·노이즈를 도메인 랜덤화로 모델링하세요.
- 정책용 저수준 경로: `legs_move()`는 내부 큐/스레드로 보간하므로 50Hz 정책에는 지연이 생깁니다. robot-hat 서보 직접 쓰기 모드를 드라이버에 추가하세요.
- 서보 12개 동시 부하 시 전압 강하로 I2C 에러가 날 수 있으니 재시도·워치독을 유지하세요.
- 바닥 마찰: 미끄럼 방지 처리를 했다면 MuJoCo 발 마찰 계수도 맞추고 도메인 랜덤화 범위를 넉넉히 두세요.
- 제어 루프 지터를 줄이려면 추론·발행을 전용 스레드에 두고, 필요하면 `isolcpus`로 코어 하나를 떼어 주세요.

## 추천 진행 순서

1. ✅ 호스트에서 PiDog 예제 동작 확인
2. ✅ Docker ROS 2 + 드라이버로 `/imu/data`, 관절 명령 확인
3. ✅ rosbridge + 웹/모바일 조종
4. URDF 작성 → Foxglove에서 TF가 실물 자세와 일치하는지 확인
5. `pidog_sim_mujoco` 노드 → `sim:=true/false`만 바꿔 정책 노드를 그대로 실행
6. 실물 정책 테스트 (몸체를 띄운 상태 → 지면)
7. FSM, 인지, 음성 노드 → 마지막에 LLM/VLA 계층

---
이전: [7. 트러블슈팅](07-troubleshooting.md) · [README로](../README.md)

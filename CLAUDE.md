# PiDog ROS 2 프로젝트

## 환경
- 하드웨어: Raspberry Pi 5 + SunFounder PiDog (Robot HAT, 서보 12개, SH3001 IMU)
- 호스트: Raspberry Pi OS 64-bit. ROS 2 Lyrical은 Docker 컨테이너 `pidog` 안에서만 실행됨
- 컨테이너는 Ubuntu 26.04 / Python 3.14. 파이썬 패키지는 apt(python3-xxx) 우선, 없으면 pip --break-system-packages
- ./ws 는 컨테이너의 /ws 로 마운트됨 (colcon 워크스페이스)
- RMW: rmw_zenoh_cpp (라우터는 `pidog-zenoh` 컨테이너)

## 패키지
- pidog_driver: driver_node (cmd_vel, pidog/action, joint_commands 구독 / imu/data, joint_states 발행)
- pidog_bringup: robot.launch.py (driver + rosbridge 9090 + 웹 8080)

## 자주 쓰는 명령
- 빌드: docker exec pidog bash -c "cd /ws && colcon build --symlink-install"
- 재시작: docker compose restart pidog
- 로그: docker compose logs --tail 100 pidog
- 토픽 확인: docker exec pidog bash -c "source /ws/install/setup.bash && ros2 topic list"

## 규칙 (중요)
- Pidog() 인스턴스는 driver_node 하나에서만 생성한다. 다른 노드나 테스트 스크립트에서 Pidog()를 생성하지 않는다.
- 로봇을 움직이는 명령(/cmd_vel, /pidog/action, /joint_commands 발행, driver 재시작)은 실행 전에 반드시 사용자에게 확인한다.
- 관절 각도는 도(degree) 단위, ±90도 안전 한계를 유지한다.
- 컨테이너 안에서 apt/pip로 설치한 패키지는 확인 후 반드시 Dockerfile에도 반영한다.
- 코드 수정 후에는 빌드와 로그로 에러가 없는지 확인하고 결과를 요약한다.

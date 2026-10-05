# stream-playback-lab

Android Media3 기반 VOD 및 라이브 스트리밍을 학습하기 위한 개인 프로젝트입니다. 프로젝트명은 임시이며, 현재는 **로컬 HLS VOD의 첫 실험 구현** 단계입니다.

서버에서 제공한 MP4를 재생했던 경험을 확장해, 직접 소유하거나 사용 권한이 있는 원본을 다중 비트레이트 HLS로 변환·제공하고, ABR·탐색·버퍼링·네트워크 오류 복구를 검증하는 것이 목적입니다. 이번 입력은 FFmpeg가 생성한 패턴 영상과 사인파 음원만 사용합니다.

## 이번 구현

- 합성 원본 MP4 → H.264/AAC 360p·720p → 2초 MPEG-TS 세그먼트와 HLS VOD 플레이리스트.
- `127.0.0.1:8090` HTTP 서버: 세그먼트 전송 속도 제한과 503 오류 주입.
- Compose 화면과 Media3 ExoPlayer: 재생·일시정지·탐색·로딩·오류·수동 재시도, Auto/수동 화질 선택.
- 요청 화질과 디코더 입력 화질, 버퍼 길이, 대역폭 추정, 상태 이벤트 관찰.

실험은 제한된 로컬 환경에서 진행합니다. 유료 인프라나 실제 개인 데이터는 사용하지 않습니다. 라이브 입력·인코딩·갱신되는 플레이리스트·live edge·지연·재연결은 이후 별도 실험입니다. 현재 구현을 서비스 수준의 성능이나 안정성 검증으로 해석하지 않습니다.

## 실행

FFmpeg(`libx264`, AAC), Python 3.9 이상, JDK 17 이상, Android SDK 플랫폼 36와 Build Tools 36.0.0, adb가 필요합니다. `ANDROID_HOME`은 본인의 SDK 위치로 설정합니다. 전용 AVD 스크립트는 설치된 API 34 Google APIs Play Store 시스템 이미지를 사용하며, `LAB_SYSTEM_IMAGE`로 다른 설치된 이미지를 지정할 수 있습니다.

```bash
scripts/generate_hls.sh 180
python3 scripts/serve_hls.py
```

서버를 실행해 둔 상태에서 다른 터미널로 전용 AVD와 앱을 준비합니다. 8090과 5558 포트가 비어 있어야 합니다.

```bash
scripts/start_emulator.sh
```

AVD 부팅 후 다른 터미널에서:

```bash
scripts/check.sh
"$ANDROID_HOME/platform-tools/adb" -s emulator-5558 reverse tcp:8090 tcp:8090
"$ANDROID_HOME/platform-tools/adb" -s emulator-5558 install -r app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/platform-tools/adb" -s emulator-5558 shell am start -n dev.easyhooon.streamplaybacklab/.MainActivity
```

`adb reverse`가 기기 자신의 loopback을 호스트의 loopback으로 연결합니다. 서버는 외부 인터페이스에 바인딩하지 않으며 앱의 평문 HTTP 허용도 localhost로 제한합니다. 실제 USB 기기도 자신의 serial을 명시하고 동일한 reverse 연결을 사용합니다.

## 검증과 실험

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
scripts/test_ui.sh emulator-5558
python3 scripts/verify_playback.py --serial emulator-5558
```

마지막 명령은 **선택한 전용 기기**의 앱을 다시 시작하고 재생·정지·탐색, 6 Mbps → 600 kbps → 6 Mbps의 자동 화질 전환, 503 오류 후 재시도를 확인합니다. Auto 모드에서 `ADAPTIVE` 요청 이벤트와 디코더 화질 변경이 모두 있어야 통과합니다. 기기·인코더·운영체제에 따라 시간과 결과는 달라질 수 있습니다.

속도 제한은 `.ts` 응답마다 적용하는 애플리케이션 수준 실험이며 전체 네트워크 링크의 정밀한 에뮬레이션은 아닙니다. 기본 설정에서 여러 연결의 합산 처리량이나 OS 전반의 네트워크를 제한하지 않습니다.

생성 영상·APK·로그·스크린샷·AVD·Gradle 캐시는 `.local/`과 빌드 폴더에 보관하며 Git에서 제외합니다. 자세한 연결 설명과 직접 바꿔볼 실험은 [학습 노트](docs/learning.md), 실제 확인 범위는 [검증 기록](docs/verification.md)을 참고하세요.

종료할 때는 서버 터미널에서 Ctrl+C를 누르고, 전용 AVD만 아래 명령으로 종료합니다.

```bash
"$ANDROID_HOME/platform-tools/adb" -s emulator-5558 emu kill
```

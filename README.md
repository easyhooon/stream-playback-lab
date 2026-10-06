# stream-playback-lab

Android Media3 기반 VOD 및 라이브 스트리밍을 학습하기 위한 개인 프로젝트입니다. 프로젝트명은 임시이며, 현재는 **로컬 VOD와 일반 라이브 HLS 실험** 단계입니다.

서버에서 제공한 MP4를 재생했던 경험을 확장해, 직접 소유하거나 사용 권한이 있는 원본을 다중 비트레이트 HLS로 변환·제공하고, ABR·탐색·버퍼링·네트워크 오류 복구를 검증하는 것이 목적입니다. FFmpeg가 생성한 패턴 영상·사인파와 CC BY 3.0으로 제공되는 Big Buck Bunny의 짧은 구간을 입력으로 사용합니다.

## 이번 구현

- 합성 원본 MP4 → H.264/AAC 360p·720p → 2초 MPEG-TS 세그먼트와 HLS VOD 플레이리스트.
- Python 표준 `ThreadingHTTPServer`, `127.0.0.1:8090`: 미디어 제공, 세그먼트 전송 속도 제한과 503 오류 주입.
- 실제 시간으로 생성하는 합성 라이브: 2초 세그먼트 6개의 이동 창, 플레이리스트 갱신, 송출 중단/재시작.
- 공식 Big Buck Bunny 원본의 짧은 구간: 360p/720p/1080p VOD. [출처·CC BY 3.0·가공 내역](docs/media-sources.md).
- Compose 화면과 Media3 ExoPlayer: 재생·일시정지·탐색·로딩·오류·수동 재시도, Auto/수동 화질 선택.
- 요청 화질과 디코더 입력 화질, 버퍼 길이, 대역폭 추정, 상태 이벤트 관찰.
- 라이브 offset·창 끝 시각과 라이브 복귀 관찰. 일반 HLS이며 LL-HLS가 아닙니다.

실험은 제한된 로컬 환경에서 진행합니다. 유료 인프라·실제 개인 데이터·카메라/마이크 권한은 사용하지 않습니다. 현재 구현을 서비스 수준의 성능이나 안정성 검증으로 해석하지 않습니다.

## 로컬 서버 실행

현재는 **로컬 파일 제공** 단계입니다. AWS·CDN에 배포하지 않았으며 AWS 계정, 결제 연결, 도메인이나 외부 포트 공개는 필요하지 않습니다. 아래 명령은 macOS/Linux의 Bash 환경에서 저장소 루트를 기준으로 실행합니다.

| 구성 | 준비/실행 | 앱에서 선택 / HTTP 경로 |
| --- | --- | --- |
| 합성 VOD | FFmpeg로 한 번 생성 | VOD / `/hls/master.m3u8` |
| Big Buck Bunny VOD (선택) | 공식 원본의 짧은 구간만 변환 | Bunny / `/bbb/master.m3u8` |
| 합성 라이브 | HTTP 서버의 `--live`가 소유한 FFmpeg로 계속 생성 | Live / `/live/index.m3u8` |
| 미디어 HTTP 서버 | Python 표준 `ThreadingHTTPServer` 하나 | `127.0.0.1:8090`, `/status` |

### 1. 필요한 도구와 checkout

- 서버/미디어: Git, Bash, Python 3.9 이상, FFmpeg와 ffprobe (`libx264`, AAC, HLS 지원), curl. Python 외부 패키지 설치는 필요하지 않습니다.
- Android 앱: JDK 17 이상, Android SDK 플랫폼 36, Build Tools 36.0.0, Platform-Tools(adb). Gradle은 저장소의 wrapper를 사용하며 최초 빌드에 Gradle·Maven 다운로드가 필요합니다.
- 전용 AVD: SDK Emulator와 Command-line Tools(`latest`), **설치된** API 34 Google APIs Play Store 이미지. Apple Silicon은 `arm64-v8a`, Intel/AMD는 `x86_64`를 기본 사용합니다. `LAB_SYSTEM_IMAGE`로 다른 설치된 이미지를 지정할 수 있습니다. AVD 생성 스크립트는 시스템 이미지를 내려받지 않습니다.

```bash
git clone https://github.com/easyhooon/stream-playback-lab.git stream-playback-lab
cd stream-playback-lab
python3 --version
ffmpeg -version
ffprobe -version
```

Android SDK는 본인의 설치 위치를 지정합니다. **앱/AVD 명령을 실행하는 각 터미널**에서 설정하세요. 서버만 실행할 때는 SDK가 필요하지 않습니다.

```bash
# macOS 기본 SDK 위치의 예. Linux 기본 위치는 "$HOME/Android/Sdk".
export ANDROID_HOME="$HOME/Library/Android/sdk"
java -version
"$ANDROID_HOME/platform-tools/adb" version
```

서버 포트 8090, AVD 포트 5558·5559가 비어 있어야 합니다. `lsof -nP -iTCP:8090 -sTCP:LISTEN`으로 기존 서버를 확인할 수 있으며, 출력이 없으면 listener가 없습니다. 다른 작업이 쓰고 있으면 그 프로세스를 종료하지 말고 사용이 끝난 뒤 진행합니다. 앱의 미디어 주소는 8090으로 고정되어 있습니다.

### 2. VOD 파일 준비 — 처음 한 번

```bash
scripts/generate_hls.sh 180
```

`Generated 180s synthetic VOD ...`가 나오고 `.local/media/hls/master.m3u8`, `360p/index.m3u8`, `720p/index.m3u8`와 `.ts`가 생성되면 준비된 것입니다. 매번 서버를 시작할 때 재생성할 필요는 없습니다. 입력 변경 시에만 다시 실행합니다.

Bunny는 선택 사항입니다. 생략해도 합성 VOD와 라이브가 동작합니다. 앱에서 Bunny를 선택하려면 아래 준비가 필요합니다.

```bash
if [ -f .local/media/bbb/master.m3u8 ]; then
    echo "기존 Bunny HLS를 사용합니다."
else
    scripts/prepare_bunny.sh 30 30
fi
```

처음에는 공식 1080p 원본 ZIP 약 263 MiB를 내려받아 체크섬을 검사하고, **30..60초 구간만** 360p/720p/1080p H.264/AAC로 변환합니다. 완성된 HLS가 있으면 위 명령은 재인코딩을 건너뜁니다. `prepare_bunny.sh`를 직접 재실행하면 원본 ZIP/MP4는 재사용하지만 지정 구간은 다시 인코딩합니다. 생성 중인 파일을 재생하지 말고 완료 메시지를 기다리세요.

Big Buck Bunny: **© 2008 Blender Foundation / www.bigbuckbunny.org**, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). 구간 추출·크기 변경·재인코딩한 실험 입력입니다. [공식 원본·귀속·가공 내역](docs/media-sources.md).

### 3. HTTP 서버와 라이브 — 터미널 A

저장소 루트에서 아래 프로세스를 실행해 둡니다.

```bash
python3 scripts/serve_hls.py --live
```

`Loopback HLS: http://127.0.0.1:8090/hls/master.m3u8`와 `Ordinary live HLS: http://127.0.0.1:8090/live/index.m3u8`가 출력됩니다. 이 **한 서버**가 합성 VOD·Bunny·라이브를 모두 제공합니다. `--live`는 사인파와 패턴 영상의 실시간 생성·인코딩도 시작합니다. 첫 라이브 플레이리스트는 첫 2초 세그먼트가 완성된 후 게시됩니다.

VOD만 필요하면 위 프로세스 대신 `python3 scripts/serve_hls.py`를 사용합니다. 두 서버를 동시에 같은 포트에서 실행하지 않습니다. `--live` 없이 실행할 때는 합성 VOD master가 먼저 있어야 하며 라이브 제어 요청은 409를 반환합니다. 남아 있는 이전 라이브 파일의 HTTP 200 응답만으로 송출 중이라고 판단하지 말고 `/status`와 갱신 여부를 확인하세요.

### 4. 서버 성공 확인 — 다른 터미널

같은 저장소 루트에서 실행합니다. HTTP 200, 초기 `kbps: 0`, `fail: false`, 라이브의 `running: true`를 확인합니다. `running`은 인코더 프로세스 상태이고, 실제 게시 여부는 아래 플레이리스트·세그먼트 요청으로 확인합니다.

```bash
curl --fail --silent --show-error http://127.0.0.1:8090/status | python3 -m json.tool
curl --fail --silent --show-error http://127.0.0.1:8090/hls/master.m3u8
curl --fail --silent --show-error http://127.0.0.1:8090/hls/360p/index.m3u8
curl --fail --silent --show-error http://127.0.0.1:8090/hls/720p/index.m3u8
mkdir -p .local/checks
curl --fail --silent --show-error http://127.0.0.1:8090/hls/360p/segment_000.ts -o .local/checks/vod.ts
ffprobe -v error -show_entries stream=codec_name,width,height,channels -of json .local/checks/vod.ts
```

master에는 360p·720p 변형이, 하위 플레이리스트에는 `EXTINF`와 `EXT-X-ENDLIST`가 있어야 합니다. ffprobe는 H.264 640×360과 AAC stereo를 보여 줍니다. Bunny를 준비했다면 다음도 HTTP 200이어야 합니다. master에는 세 화질이 표시됩니다.

```bash
curl --fail --silent --show-error http://127.0.0.1:8090/bbb/master.m3u8
curl --fail --silent --show-error http://127.0.0.1:8090/bbb/1080p/index.m3u8
curl --fail --silent --show-error http://127.0.0.1:8090/bbb/1080p/segment_000.ts -o .local/checks/bunny.ts
ffprobe -v error -show_entries stream=codec_name,width,height,channels -of json .local/checks/bunny.ts
```

라이브 세그먼트 이름은 계속 바뀌므로 현재 플레이리스트에서 읽어 요청합니다. 첫 게시 전 404이면 잠시 후 다시 실행합니다.

```bash
python3 - <<'PY'
from urllib.parse import urljoin
from urllib.request import urlopen
url = "http://127.0.0.1:8090/live/index.m3u8"
with urlopen(url, timeout=5) as response:
    playlist = response.read().decode()
segments = [line for line in playlist.splitlines() if line and not line.startswith("#")]
assert 1 <= len(segments) <= 6
assert "#EXT-X-PROGRAM-DATE-TIME:" in playlist
assert "#EXT-X-ENDLIST" not in playlist
with urlopen(urljoin(url, segments[-1]), timeout=5) as response:
    data = response.read()
assert data
print(playlist)
print("Live segment OK:", segments[-1], "bytes:", len(data))
PY
```

15초 이상 뒤 다시 실행하면 MEDIA-SEQUENCE와 세그먼트 목록이 앞으로 이동해야 합니다. 창은 최대 6개 × 2초(약 12초)이며 일반 HLS입니다. 라이브 생성 오류는 `.local/live-encoder.log`에서 확인합니다.

### 5. Android 앱 연결

AVD가 필요한 경우, 다른 기기 검증과 겹치지 않는 시간에 **터미널 B**에서 시작해 둡니다.

```bash
scripts/start_emulator.sh
```

이 스크립트는 `.local/avd/`의 `Stream_Playback_Lab`을 `emulator-5558`로 실행합니다. 기본 설정은 화면 창·오디오 출력 없는 AVD입니다. 다른 터미널에서 `ANDROID_HOME`을 설정한 뒤:

```bash
LAB_SERIAL=emulator-5558
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" wait-for-device
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" shell getprop sys.boot_completed
```

마지막 응답이 `1`일 때 아래를 진행합니다. `wait-for-device`만으로 전체 부팅이 끝난 것은 아닙니다. 실제 USB 기기를 쓸 때는 `LAB_SERIAL`을 그 기기의 serial로 지정하고 AVD 시작을 생략합니다.

```bash
scripts/check.sh :app:assembleDebug
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" reverse tcp:8090 tcp:8090
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" reverse --list
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" install -r app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" shell am start -n dev.easyhooon.streamplaybacklab/.MainActivity
```

빌드의 `BUILD SUCCESSFUL`, reverse 목록의 `tcp:8090 tcp:8090`, 설치의 `Success`를 확인합니다. 앱 VOD에서 READY·Playing, Bunny 준비 후 Bunny에서 실제 원작 구간, Live에서 `dynamic=true`와 변하는 창 끝 시각을 확인합니다. `adb reverse`가 **선택한 기기 자신의 loopback**을 호스트로 연결합니다. 기기를 재부팅/재연결하면 reverse를 다시 설정합니다. 외부 인터페이스 바인딩이나 앱의 localhost HTTP 제한을 바꾸지 않습니다.

### 6. 중단과 다시 시작

라이브 **송출만** 중단/재시작하려면 HTTP 서버가 실행 중인 상태에서:

```bash
curl --fail --silent --show-error -X POST http://127.0.0.1:8090/live-control -H 'Content-Type: application/json' -d '{"running":false}'
curl --fail --silent --show-error -X POST http://127.0.0.1:8090/live-control -H 'Content-Type: application/json' -d '{"running":true}'
```

각 응답의 `running: false/true`를 확인합니다. 중단 중에도 VOD HTTP 제공은 계속되고, 라이브 파일은 마지막 상태로 남습니다. 재시작은 이전 라이브 파일을 정리하고 새 시퀀스·시간 원점으로 게시합니다. 새 세그먼트가 나온 뒤 앱의 Retry를 누릅니다.

**서버 전체 종료:** 터미널 A에서 Ctrl+C. 서버의 정리 경로가 자신이 시작한 FFmpeg도 종료합니다. 재실행은 같은 `python3 scripts/serve_hls.py --live` 명령이며, 완성된 VOD/Bunny는 재생성하지 않아도 됩니다.

**기기 연결 종료:** 선택한 기기의 이 reverse만 제거합니다.

```bash
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" reverse --remove tcp:8090
```

직접 시작한 전용 AVD는 아래로 이름을 확인합니다. `Stream_Playback_Lab` 응답을 확인한 경우에만 뒤의 종료 명령을 실행합니다. USB 기기에는 AVD 종료 명령을 적용하지 않습니다.

```bash
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" emu avd name
```

```bash
"$ANDROID_HOME/platform-tools/adb" -s "$LAB_SERIAL" emu kill
```

### 자주 만나는 문제

| 증상 | 확인/해결 |
| --- | --- |
| `Address already in use` | 8090의 기존 listener를 확인합니다. 본인이 시작한 영상 서버라면 그 터미널에서 Ctrl+C 후 재시작합니다. 앱은 8090을 사용하므로 서버 포트만 바꾸면 연결되지 않습니다. |
| `Run scripts/generate_hls.sh first` | VOD 파일이 없는 상태로 `--live` 없이 시작한 경우입니다. 2단계에서 합성 VOD를 생성합니다. |
| Bunny 404 | 선택 입력을 아직 준비하지 않았거나 생성 중입니다. `prepare_bunny.sh 30 30` 완료와 master 파일을 확인합니다. |
| Live 404 / 창이 멈춤 | `--live`, `/status`의 `live.running`, 첫 세그먼트 게시와 인코더 로그를 확인합니다. 송출 정지 상태의 기존 파일은 새 방송이 아닙니다. |
| `/live-control` 409 | VOD 전용 서버입니다. 그 서버를 Ctrl+C로 종료하고 `--live`로 다시 시작합니다. |
| HTTP 503 / 매우 느린 세그먼트 | 실험 설정이 남았는지 `/status`로 확인하고 아래 `/control` 초기화 후 Retry를 누릅니다. |
| `ffmpeg` 없음 / `Unknown encoder 'libx264'` | PATH와 FFmpeg의 H.264/AAC 지원을 확인합니다. `.local/live-encoder.log`에도 실패가 기록됩니다. |
| Bunny 다운로드/체크섬 실패 | 네트워크와 공식 URL을 확인합니다. 체크섬 검사를 제거하지 말고 [출처 문서](docs/media-sources.md)의 원본을 확인합니다. |
| SDK/JDK/시스템 이미지 오류 | `ANDROID_HOME`, JDK 17 이상, SDK 36·Build Tools 36.0.0, Emulator·Command-line Tools와 설치된 AVD 이미지를 확인합니다. |
| 호스트 curl은 성공, 앱은 실패 | 명시한 serial의 부팅/USB 승인 상태, reverse 목록과 재설정을 확인합니다. 앱 주소의 `127.0.0.1`은 기기 자신의 주소입니다. |

```bash
curl --fail --silent --show-error -X POST http://127.0.0.1:8090/control -H 'Content-Type: application/json' -d '{"kbps":0,"fail":false}'
```

## 검증과 실험

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
scripts/test_ui.sh emulator-5558
python3 scripts/verify_playback.py --serial emulator-5558
python3 scripts/verify_live.py --serial emulator-5558
python3 scripts/verify_bunny.py --serial emulator-5558
```

기기 검증은 **선택한 전용 기기**의 앱을 다시 시작합니다. 합성 VOD 180초·`--live` 서버·부팅된 기기를 먼저 준비하고, `verify_bunny.py`는 Bunny까지 준비한 경우에만 실행합니다. `verify_playback.py`는 기존 합성 VOD의 재생·정지·탐색, 6 Mbps → 600 kbps → 6 Mbps 자동 화질 전환과 503 복구를 확인합니다. `verify_live.py`는 실제 FFmpeg 송출의 이동 창·일시정지/복귀·중단 후 복구를, `verify_bunny.py`는 실제 원작 구간과 세 화질의 디코더 입력을 확인합니다. 기기·인코더·운영체제에 따라 시간과 결과는 달라질 수 있습니다.

속도 제한은 `.ts` 응답마다 적용하는 애플리케이션 수준 실험이며 전체 네트워크 링크의 정밀한 에뮬레이션은 아닙니다. 기본 설정에서 여러 연결의 합산 처리량이나 OS 전반의 네트워크를 제한하지 않습니다.

생성 영상·APK·로그·스크린샷·AVD·Gradle 캐시는 `.local/`과 빌드 폴더에 보관하며 Git에서 제외합니다. 서버 언어·실행·라이브 역할과 작은 실험은 [서버 설명](docs/server.md), 원본→Media3 연결은 [학습 노트](docs/learning.md), 실제 확인 범위는 [검증 기록](docs/verification.md)을 참고하세요.

이번 실행 안내의 재확인 범위와 미실행 항목은 [로컬 구동 안내 검증](docs/startup-verification.md)에 정리합니다.

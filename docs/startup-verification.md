# 로컬 구동 안내 검증

2026-10-06 UTC, README의 서버 실행 명령을 재확인했습니다. 실행 코드는 커밋 `1e20e4603e6d00b978ef755c3088b6d83e4e4616`과 같으며 이번 변경은 README와 이 문서뿐입니다. 기존 재생 실험의 기록은 [별도 검증 문서](verification.md)에 있습니다.

환경은 macOS arm64, Python 3.9.0, FFmpeg/ffprobe 8.1.2, JDK 21.0.11, SDK 플랫폼 36·Build Tools 36.0.0입니다. 실제 기기를 시작하지 않고 서버 측에서 확인했습니다.

## 실행해서 통과한 확인

| 명령/확인 | 실제 결과 |
| --- | --- |
| `git clone https://github.com/easyhooon/stream-playback-lab.git stream-playback-lab` | 새 checkout 생성, 기존 커밋과 HEAD 일치 |
| `python3 --version`, `ffmpeg -version`, `ffprobe -version`, `java -version`, SDK의 `adb version` | 도구와 위 버전 확인. adb 버전 조회는 기기에 연결하지 않음 |
| `scripts/generate_hls.sh 180` | 미디어가 없던 새 checkout에 합성 VOD 생성. 360p·720p 하위 플레이리스트 각각 2초 세그먼트 90개와 ENDLIST |
| `python3 scripts/serve_hls.py` | 8090에서 VOD 전용 서버 시작, `/status`의 `kbps: 0`, `fail: false` |
| README 4단계 VOD curl·ffprobe 명령 블록 | master·두 하위 플레이리스트·360p 첫 세그먼트 HTTP 200. H.264 640×360 / AAC stereo 확인 |
| `scripts/prepare_bunny.sh 30 30` | 캐시된 공식 ZIP의 체크섬 확인 후 30..60초 구간만 3화질로 인코딩. 전체 영화를 인코딩하지 않음 |
| README의 Bunny 파일 존재 조건 블록 재실행 | 기존 HLS 사용 메시지, master 수정 시각 유지. 재인코딩 건너뜀 |
| `python3 scripts/serve_hls.py --live` | 한 서버에서 VOD·Bunny·라이브 제공, `/status`의 `live.running: true` |
| README 4단계 Bunny curl·ffprobe 명령 블록 | master·1080p 하위 플레이리스트·첫 세그먼트 HTTP 200. H.264 1920×1080 / AAC stereo 확인. 세 화질 각각 15개 세그먼트 확인 |
| README 4단계 라이브 Python 명령 블록 | 현재 플레이리스트에서 읽은 세그먼트 HTTP 200. 최대 6개 이동 창, PROGRAM-DATE-TIME, ENDLIST 없음. 재확인 시 MEDIA-SEQUENCE 증가 |
| README의 `POST /live-control` 중단·재시작 명령 | `running: false/true`, 중단 중 플레이리스트 정지와 VOD 제공 유지, 재시작 후 새 시퀀스 확인 |
| README의 `POST /control` 초기화 명령 | 503 장애 주입 후 `kbps: 0`, `fail: false`로 복원, 미디어 HTTP 200 |
| 서버 SIGINT 종료(Ctrl+C 정리 경로) 및 같은 명령 재시작 | 소유한 서버·FFmpeg 자식 종료, 8090 닫힘. VOD/Bunny 재생성 없이 라이브 서버 재시작 |
| `python3 -m unittest discover -s scripts -p 'test_*.py' -v` | Python 서버/라이브 테스트 3개, 실패 0개, skip 없음 |
| `scripts/check.sh :app:assembleDebug` | 기존 checkout의 SDK·프로젝트 캐시로 `BUILD SUCCESSFUL`. 36개 태스크 모두 up-to-date |
| README의 Bash 블록 17개 `bash -n`, `git diff --check` | 구문·공백 검사 통과 |

서버 검증은 Git에서 제외하는 `.local/readme-smoke/`의 새 checkout에서 진행했습니다. BBB 원본 ZIP/MP4만 기존 소유 캐시를 재사용했고 HLS 출력은 새로 생성했습니다. 원시 로그와 요약은 같은 폴더의 `verification.log`, `build.log`, `report.json`에 있으며 공개 커밋에 넣지 않았습니다.

## 의도한 실패 응답 확인

정상 실행 검증에서 예상하지 않은 실패는 없었습니다. 다음은 문제 안내를 확인하기 위해 의도적으로 발생시킨 응답입니다.

| 조건 | 실제 응답 |
| --- | --- |
| 합성 VOD 생성 전에 `python3 scripts/serve_hls.py` | 종료 코드 2, `Run scripts/generate_hls.sh first, or use --live` |
| Bunny 준비 전 `/bbb/master.m3u8` | HTTP 404 |
| `--live` 없는 서버에 `POST /live-control` | HTTP 409 |
| `fail: true` 주입 후 VOD master 요청 | HTTP 503, 초기화 후 200 복원 |

## 이번에 실행하지 않은 확인

- BBB 원본의 첫 네트워크 다운로드·압축 해제: 기존 캐시를 사용했습니다. 체크섬 검사와 짧은 구간 인코딩은 다시 실행했습니다.
- 빈 캐시에서의 Gradle·Maven 다운로드: APK 명령은 기존 프로젝트 캐시로 확인했습니다.
- AVD 시작·부팅·adb reverse·설치·앱 실행·reverse 제거·AVD 종료, USB 기기와 실제 플레이어 시나리오: 다른 랩의 기기 검증과 경합하지 않도록 실행하지 않았습니다. 스크립트의 serial·경로·인자와 앱의 고정 주소는 코드로 대조했습니다.
- `scripts/test_ui.sh`, `verify_playback.py`, `verify_live.py`, `verify_bunny.py`, JVM 테스트·Android lint 재실행: 이번 문서 변경에서 새 통과 결과로 기록하지 않습니다.
- 포트 충돌, 도구/SDK 누락, 다운로드·체크섬 장애의 강제 재현, Linux·Intel/AMD 환경: 문제 안내는 코드 조건을 확인해 작성했으며 해당 환경을 이번에 실행하지 않았습니다.

검증이 시작한 서버와 인코더만 종료했고 에뮬레이터는 사용하지 않았습니다. 배포·AWS·CDN·결제 연결·새 기능·인프라 변경은 없습니다.

# 로컬 VOD·라이브 검증 기록

2026-10-05, 전용 API 34 arm64 AVD에서 합성 VOD, 일반 라이브 HLS, Big Buck Bunny의 짧은 구간을 확인했습니다. 실제 Android 하드웨어나 여러 통신 환경에서의 품질을 검증한 결과는 아닙니다.

## 조건과 기본 검사

- FFmpeg 8.1.2, Media3 1.9.3, Compose BOM 2025.08.01, AGP 9.0.1, Gradle 9.2.1, JDK 21.
- compile/target SDK 36, min SDK 26. 전용 `Stream_Playback_Lab` / `emulator-5558`에서 `adb reverse`로 `127.0.0.1:8090`에 연결.
- 합성 VOD: 180초 패턴 영상·사인파, H.264/AAC 360p·720p, 2초 MPEG-TS 세그먼트. master의 최대 BANDWIDTH는 약 499 / 2,205 kbps.
- 합성 라이브: 실시간 FFmpeg H.264/AAC 360p, 2초 세그먼트 6개의 이동 창. `PROGRAM-DATE-TIME`, 갱신되는 MEDIA-SEQUENCE, ENDLIST 없음.
- Bunny: 공식 1080p 원본의 30..60초 구간을 360p·720p·1080p H.264/AAC로 변환. [출처와 가공 조건](media-sources.md).
- VOD 두 화질과 Bunny 1080p 첫 세그먼트에서 PTS 1.466667초의 시작 키프레임을 확인했습니다. 생성 미디어는 Git에서 제외합니다.

| 검사 | 결과 |
| --- | --- |
| Debug APK 및 instrumentation APK 빌드 | 통과 |
| Android lint | 오류 0개, 고정한 의존성 버전과 target SDK 관련 경고 9개 |
| JVM 단위 테스트 | 2개 통과: 탐색 경계, 시간 표시 |
| Python 서버/송출 테스트 | 3개 통과: 속도·503·입력 검증, 라이브 창 갱신·파일 수 제한·송출 중단/재시작 |
| Compose 기기 UI 테스트 | 4개 통과: 로딩 중 Pause, 오류/Retry, 재생·탐색·화질 콜백, 라이브 선택·Go live 콜백 |

위 테스트는 총 9개입니다. 아래 실제 재생 시나리오는 별도로 실행했습니다.

## 합성 VOD 회귀

기존 VOD의 로딩·일시정지·재개·탐색, Auto의 720p → 360p → 720p 요청과 디코더 입력, 503 해제 후 Retry 복구를 모두 확인했습니다. `.ts` 응답마다 6,000 → 600 → 6,000 kbps로 제한했으며 링크 전체를 제한하는 실험은 아닙니다.

```text
decoder_format height=720 bitrate=2204864 position_ms=0
request_format height=360 reason=ADAPTIVE position_ms=27403
decoder_format height=360 position_ms=27325
request_format height=720 reason=ADAPTIVE position_ms=39365
decoder_format height=720 position_ms=39323
player_error code=ERROR_CODE_IO_BAD_HTTP_STATUS position_ms=49881
retry position_ms=49881
playing=true position_ms=49901
```

발췌에서는 일부 필드를 생략했습니다. `position_ms`는 재생 시간축의 위치이며, 속도 변경 후 경과 시간이나 지연 측정값은 아닙니다. 속도 변경 중 BUFFERING과 짧은 재버퍼링도 관찰했습니다. 끊김 없는 전환이나 특정 지연 상한을 보장하는 통과 기준은 아닙니다.

Muxed HLS의 downstream 이벤트는 이 실행에서 `TRACK_TYPE_DEFAULT`(0)이었습니다. 영상 이벤트는 `Format.height`로 식별하고 요청만이 아니라 디코더 입력과 화면을 함께 확인했습니다.

## 일반 라이브 HLS

| 실제 시나리오 | 관찰 |
| --- | --- |
| 플레이리스트 갱신 | MEDIA-SEQUENCE 증가, 최대 6개 세그먼트, PROGRAM-DATE-TIME, ENDLIST·EXT-X-PART 없음 |
| 일시정지와 복귀 | offset 8,021 ms → 14초 Pause 후 21,656 ms → Go live 후 7,672 ms |
| 송출 중단 | 소유한 FFmpeg를 실제 정지, HTTP 서버는 유지, 플레이리스트 갱신 정지와 최종 플레이어 오류 확인 |
| 송출 재시작 | 새로운 시퀀스·시간 원점, Retry 후 재생과 offset 8,027 ms 확인 |
| 최종 화면 확인 | `live=true`, `dynamic=true`, 12,000 ms 창, Playing, AAC stereo 입력, Go live와 창 끝 시각 표시 |

송출 중단 시 최종 오류는 `ERROR_CODE_IO_UNSPECIFIED`였으며 이번 로그만으로 구체적인 내부 원인을 단정하지 않습니다. 복구는 서버가 새 세그먼트를 게시한 뒤 사용자가 Retry를 누르는 시나리오입니다. 모든 장애에서 자동 복구한다고 주장하지 않습니다.

앱의 목표 offset은 6초이고 이 실행의 측정값은 대체로 약 8초였습니다. 설정값을 실제 지연 보장으로 취급하지 않습니다. 일반 HLS이며 LL-HLS 또는 촬영부터 화면 출력까지의 glass-to-glass 측정이 아닙니다. 정지 직전의 마지막 세그먼트는 2초보다 짧을 수 있습니다.

## Big Buck Bunny

실제 원작 화면과 앱의 출처·CC BY 3.0·가공 안내를 확인했습니다. 수동 선택한 세 화질에서 아래 디코더 입력을 관찰했습니다. 처음 Auto로 이미 선택한 1080p를 수동으로 유지하는 경우에는 같은 형식의 새 콜백을 요구하지 않고 현재 디코더 형식을 확인합니다.

| 화질 | 디코더 입력 BANDWIDTH |
| --- | --- |
| 360p | 606,111 bps |
| 720p | 2,558,304 bps |
| 1080p | 5,761,824 bps |

`audio_format mime=audio/mp4a-latm channels=2`로 AAC stereo 입력을 확인했고, 30초 구간이 ENDED에 도달한 뒤 Replay로 다시 재생되는 것을 확인했습니다. 에뮬레이터는 오디오 출력 없이 실행했으므로 스피커로 들은 음질이나 실제 기기의 재생 성능을 검증한 결과는 아닙니다.

## 재현 자료와 범위

[README](../README.md)의 실행 순서와 `scripts/check.sh`, `scripts/test_ui.sh`, `scripts/verify_playback.py`, `scripts/verify_live.py`, `scripts/verify_bunny.py`를 사용합니다. 세 기기 시나리오가 각각 `status: PASS`를 기록했습니다.

로컬 증거는 `.local/evidence/report.json`과 `playback.log`, `.local/evidence/live/`, `.local/evidence/bunny/`, `.local/evidence/live-final/`에 있습니다. 원본·세그먼트·APK·원시 로그·스크린샷·AVD·캐시는 Git에서 제외하고, 공개 저장소에는 재현 코드와 요약만 보관합니다. 재실행하면 증거가 갱신됩니다.

검증 후 소유한 라이브 인코더·HTTP 서버와 전용 AVD를 종료하고 8090·5558 포트가 닫힌 것을 확인했습니다. 이번 범위에는 DRM, CDN, 계정/결제, 다운로드, 백그라운드 미디어 서비스나 전체 서비스 수준의 성능 검증이 없습니다.

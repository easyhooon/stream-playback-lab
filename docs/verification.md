# 로컬 VOD 검증 기록

2026-10-05, 독립 API 34 arm64 AVD에서 확인한 첫 실험입니다. 실제 Android 하드웨어나 여러 통신 환경에서의 품질을 검증한 결과는 아닙니다.

## 조건

- FFmpeg 8.1.2로 직접 생성한 180초 패턴 영상과 사인파 음원.
- HLS VOD: 360p / 720p, H.264 + AAC, 2초 MPEG-TS 세그먼트. master의 최대 BANDWIDTH는 약 499 / 2,205 kbps.
- FFprobe로 양쪽 첫 세그먼트가 동일한 PTS 1.466667초의 키프레임으로 시작하는 것을 확인했고, 플레이리스트의 VOD·ENDLIST·2초 구간을 확인.
- Media3 1.9.3, Compose BOM 2025.08.01, AGP 9.0.1, Gradle 9.2.1, JDK 21로 빌드. compile/target SDK 36, min SDK 26.
- 전용 `Stream_Playback_Lab` / `emulator-5558`에서 `adb reverse`로 `127.0.0.1:8090`에 연결.
- 서버 `.ts` 응답마다 6,000 → 600 → 6,000 kbps로 제한. 링크 전체를 제한하는 실험은 아니며 시간값은 환경에 따라 달라짐.

## 확인 결과

| 항목 | 결과 |
| --- | --- |
| Debug APK 및 instrumentation APK 빌드 | 통과 |
| Android lint | 통과: 오류 0개, 고정한 의존성 버전과 target SDK 관련 경고 9개 |
| JVM 단위 테스트 | 2개 통과: 탐색 경계, 시간 표시 |
| Python 서버 테스트 | 2개 통과: 속도 제한·503·복구, 경로/입력 검증 |
| Compose 기기 UI 테스트 | 3개 통과: 로딩 중 Pause, 오류/Retry, 재생·탐색·화질 콜백 |
| 실제 재생 | 720p 디코더 입력, READY·Playing 및 움직이는 영상 화면 확인 |
| 일시정지 및 재개 | Pause 후 3초 동안 화면의 재생 시간이 유지되고 Play 후 재개 |
| 탐색 | +10s를 누른 뒤 실제 재생 시간의 증가 확인 |
| ABR | Auto에서 수동 override 없이 720p → 360p → 720p 요청과 디코더 입력 확인 |
| 오류 및 재시도 | 주입한 503으로 최종 오류 표시, 장애 해제 후 Retry로 해당 위치에서 재개 |

속도 제한 전환 중 BUFFERING과 짧은 재버퍼링도 관찰했습니다. 이번 통과 기준은 자동 선택과 복구의 동작 확인이며, 끊김 없는 전환이나 특정 지연 상한을 보장하는 기준은 아닙니다. 수동 화질 버튼은 UI 콜백 테스트를 통과했지만 별도의 실제 디코더 전환 시나리오로 측정하지 않았습니다.

ABR과 복구에서 발췌한 이벤트입니다. `position_ms`는 재생 시간축의 위치이며, 속도 변경 후 경과 시간이나 지연 측정값은 아닙니다.

```text
request_format height=720 reason=INITIAL position_ms=0
decoder_format height=720 position_ms=0
request_format height=360 reason=ADAPTIVE position_ms=27373
decoder_format height=360 position_ms=27373
request_format height=720 reason=ADAPTIVE position_ms=39333
decoder_format height=720 position_ms=39343
player_error code=ERROR_CODE_IO_BAD_HTTP_STATUS position_ms=47877
retry position_ms=47877
playing=true position_ms=47896
```

HLS 세그먼트는 영상과 음원을 함께 담으므로 downstream 이벤트의 트랙 유형은 이 실행에서 `TRACK_TYPE_DEFAULT`(0)이었습니다. 영상 이벤트는 `Format.height`가 있는 것으로 식별했습니다. 요청 이벤트만으로 검증을 끝내지 않고 디코더 입력과 실제 화면을 함께 확인했습니다.

## 재현 자료

`scripts/check.sh`, `scripts/test_ui.sh`, `scripts/verify_playback.py`와 [README](../README.md)의 실행 절차를 사용합니다. 실제 시나리오 검증은 5개 체크가 모두 참인 `status: PASS`를 기록했습니다.

원본·세그먼트·APK·원시 로그·스크린샷은 Git에서 제외했습니다. 동일 환경의 로컬 증거는 `.local/evidence/report.json`, `playback.log`, `01-playing-720p.png`부터 `05-recovered.png`에 있으며 재실행하면 갱신됩니다. 공개 저장소에는 재현 코드와 이 요약만 보관합니다.

이번 범위에는 라이브 송출, DRM, CDN, 계정/결제, 다운로드, 백그라운드 미디어 서비스가 없습니다. 이런 기능이나 전체 서비스 수준의 성능을 검증했다고 주장하지 않습니다.

# 서버는 어떻게 구성되어 있나

HTTP 서버는 **Python 표준 라이브러리 `http.server.ThreadingHTTPServer`**입니다. 별도 웹 프레임워크나 유료 인프라를 사용하지 않습니다. FFmpeg는 영상 생성·인코딩·HLS 패키징을 맡는 외부 프로세스입니다.

| 역할 | 구현 | 실행/주소 |
| --- | --- | --- |
| 합성 VOD 생성·패키징 | Bash + FFmpeg, 미리 완성한 360p/720p 파일 | `scripts/generate_hls.sh 180` |
| Big Buck Bunny VOD | 공식 원본 다운로드 + 짧은 구간 360p/720p/1080p 재인코딩 | `scripts/prepare_bunny.sh 30 30` |
| 파일 HTTP 제공 | Python 표준 HTTP 서버 | `python3 scripts/serve_hls.py` |
| 합성 라이브 송출 | Python `LiveSource`가 소유한 FFmpeg 한 프로세스 | `python3 scripts/serve_hls.py --live` |
| 앱 재생 | Compose + Media3 ExoPlayer | VOD / Bunny / Live 선택 |

VOD에서는 변환을 먼저 끝낸 뒤 고정된 master·하위 플레이리스트·세그먼트를 읽어 줍니다. 라이브에서는 FFmpeg가 `-re`로 합성 영상과 사인파를 실시간 속도로 읽고 H.264/AAC를 계속 인코딩합니다. 서버는 인코더의 출력 파일을 HTTP로 읽어 주는 역할이며 직접 코덱을 구현하지 않습니다.

## 로컬 실행

```bash
scripts/generate_hls.sh 180
scripts/prepare_bunny.sh 30 30
python3 scripts/serve_hls.py --live
```

서버는 `127.0.0.1:8090`에만 바인딩합니다. 외부 포트 공개·방화벽 변경은 없습니다. 앱 기기에는 `adb -s <serial> reverse tcp:8090 tcp:8090`을 설정합니다.

- 합성 VOD: `/hls/master.m3u8`
- Big Buck Bunny: `/bbb/master.m3u8`
- 합성 라이브: `/live/index.m3u8`
- 상태: `/status`
- HTTP 실험: `POST /control`의 `kbps` / `fail`
- 라이브 송출 제어: `POST /live-control`의 `running`

`--live`를 생략하면 FFmpeg 송출 프로세스를 시작하지 않으며 `/live-control`은 409를 반환합니다. 송출 제어는 이 서버가 시작한 FFmpeg에만 적용합니다. 다른 앱이나 FFmpeg 프로세스를 찾거나 종료하지 않습니다.

`kbps`는 `.ts` 응답 하나마다 바이트 전송 전에 기다리는 속도 제한입니다. 여러 연결의 합산 처리량이나 OS 전체 네트워크를 제한하지 않습니다. `fail`은 HTTP 제공 실패를 주입합니다. **송출 중단**은 FFmpeg를 실제로 정지해 플레이리스트 갱신이 멈추는 실험이므로 HTTP 503 실험과 다릅니다.

## 일반 라이브 HLS

라이브는 640×360 한 화질, 2초 세그먼트 6개(약 12초)의 이동 창입니다. FFmpeg는 완성한 `.tmp` 파일을 rename하여 게시하고, 서버는 `.tmp`를 제공하지 않습니다. 플레이리스트는 읽은 바이트와 Content-Length를 같은 스냅샷으로 응답해 갱신 중 길이 불일치를 피합니다. 참조에서 벗어난 세그먼트는 두 개를 추가로 유지한 뒤 정리합니다.

`PROGRAM-DATE-TIME`이 미디어 시간과 실제 시각을 연결합니다. 창의 끝 시각과 Media3의 `currentLiveOffset`을 표시하며 앱의 목표 offset은 6초입니다. 화면의 duration/position은 전체 방송 길이와 절대 위치가 아닌 **현재 이동 창 기준**입니다. `Go live`는 최신 창의 기본 재생 위치로 돌아갑니다.

송출을 중단할 때 ENDLIST를 추가하지 않아 방송 종료 대신 갱신 정지를 재현합니다. 재시작은 새로운 시퀀스·시간 원점을 만들고 이전 라이브 파일을 정리합니다. 라이브 Retry는 미디어를 다시 로드해 새 창에서 시작하며, VOD Retry는 기존 재생 위치를 보존합니다.

부분 세그먼트, `EXT-X-PART`, blocking playlist reload를 구현하지 않았습니다. 이 프로젝트의 라이브는 **일반 HLS**이며 LL-HLS나 서브초 지연 검증이 아닙니다.

## 작은 실험

**예측:** 라이브 화면을 14초 일시정지하면 영상은 멈춰 있는데 live offset과 플레이리스트의 MEDIA-SEQUENCE는 어떻게 바뀔까요?

직접 Pause → 14초 대기 → Go live를 해 보고 offset을 비교합니다. 그다음 아래 두 명령으로 송출 중단·복구를 관찰합니다. 서버 HTTP 프로세스는 계속 실행합니다.

```bash
curl -X POST http://127.0.0.1:8090/live-control -H 'Content-Type: application/json' -d '{"running":false}'
curl -X POST http://127.0.0.1:8090/live-control -H 'Content-Type: application/json' -d '{"running":true}'
```

새 플레이리스트가 나온 뒤 앱의 Retry를 누릅니다. 목표 offset은 설정값이며 실제 측정값과 같다고 가정하지 않습니다. 표시한 offset은 카메라 촬영부터 화면 출력까지의 glass-to-glass 측정값도 아닙니다.

참고: [Media3 라이브 재생](https://developer.android.com/media/media3/exoplayer/live-streaming), [FFmpeg HLS muxer](https://ffmpeg.org/ffmpeg-formats.html#hls-2).

# 원본에서 Media3까지

Android에서 `MediaItem.fromUri()`로 MP4를 넣을 때는 서버에 이미 준비된 한 가지 미디어 표현을 읽습니다. 이 실험에서는 서버에 놓이는 파일을 만드는 과정부터 직접 관찰합니다.

1. **원본**: FFmpeg의 `testsrc2`와 `sine`으로 움직이는 영상과 음원을 생성해 `.local/media/source.mp4`로 저장합니다. 외부 영상이나 개인 데이터를 받지 않습니다.
2. **인코딩**: 같은 시간축의 원본을 640×360 / 1280×720으로 인코딩합니다. 영상 목표 비트레이트는 350 / 1,800 kbps이고 오디오는 64 / 96 kbps입니다. 실제 네트워크에는 컨테이너와 코덱 오버헤드도 포함됩니다.
3. **패키징**: 두 화질 모두 30 fps, 60프레임 GOP를 사용해 약 2초마다 키프레임을 맞추고 `.ts` 세그먼트로 나눕니다. `master.m3u8`에는 화질별 대역폭·해상도·하위 플레이리스트가, 각 `index.m3u8`에는 시간순 세그먼트와 VOD 종료 표시가 들어갑니다.
4. **HTTP 로딩**: Media3는 master와 선택한 화질의 플레이리스트를 읽고 다음 세그먼트를 요청합니다. ExoPlayer의 ABR이 대역폭 추정, 버퍼, 기기의 지원 형식을 바탕으로 다음 요청을 선택합니다. Compose는 `PlaybackUiState`와 콜백으로 화면을 그리고, `PlaybackSession`이 플레이어·관찰 이벤트를 소유합니다.

`Auto`는 수동 `TrackSelectionOverride`를 제거합니다. `Request`는 downstream 형식 이벤트로 확인한 요청 화질, `Decoder`는 비디오 디코더의 입력 형식입니다. 이미 버퍼에 담긴 세그먼트가 있어 두 값이 바로 일치하지 않을 수 있습니다. 디코더 입력 변화는 단순한 트랙 설정 변화보다 강한 증거지만, 모든 프레임의 화면 출력 품질이나 서비스 전체 성능을 측정한 것은 아닙니다.

버퍼 설정은 최소 3초·최대 15초, 시작 0.5초·재버퍼 후 재개 1초입니다. 초기 대역폭 추정은 6 Mbps로 고정해 실험의 시작 조건을 맞춥니다. 이후 추정은 실제 미디어 전송으로 바뀝니다. Media3의 로드 오류 정책에는 최소 재시도 기준을 2회로 설정했고, 실제 재시도와 트랙 fallback은 오류 종류와 정책에 따릅니다. 최종 오류에는 화면의 Retry로 현재 미디어를 다시 prepare합니다. 정책 내부의 재시도와 사용자의 Retry는 별개입니다.

**예측 질문:** 720p 재생 중 서버를 600 kbps로 낮추면 `Request`, `Decoder`, 버퍼 길이 중 무엇이 먼저 바뀔까요? 현재 버퍼에 720p 세그먼트가 얼마나 남았는지까지 생각한 뒤 이벤트를 비교해 보세요.

**직접 바꿔볼 실험:** 앱을 Auto로 재생하고 아래처럼 속도를 바꿉니다. `kbps: 0`은 제한을 해제합니다.

```bash
curl -X POST http://127.0.0.1:8090/control -H 'Content-Type: application/json' -d '{"kbps":600}'
curl -X POST http://127.0.0.1:8090/control -H 'Content-Type: application/json' -d '{"kbps":6000}'
```

600 대신 300을 넣어 가장 낮은 화질의 미디어 전송량도 감당할 수 없을 때 버퍼와 BUFFERING을 관찰합니다. 확인 후 6000 또는 0으로 되돌립니다. 정밀한 통신사 네트워크 모델이 아닌 localhost의 세그먼트 응답 속도 제한입니다.

503 장애를 직접 확인하려면 `{"fail":true}`를 전송하고, 오류가 보이면 `{"fail":false}`를 전송한 뒤 Retry를 누릅니다. 앱을 백그라운드로 보내면 재생을 일시정지하며, 다시 화면으로 돌아온 뒤 Play로 재개합니다.

참고: [Media3 HLS](https://developer.android.com/media/media3/exoplayer/hls), [트랙 선택](https://developer.android.com/media/media3/exoplayer/track-selection), [AnalyticsListener](https://developer.android.com/media/media3/exoplayer/analytics), [FFmpeg HLS muxer](https://ffmpeg.org/ffmpeg-formats.html#hls).

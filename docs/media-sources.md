# 미디어 출처와 가공

## 합성 입력

합성 VOD와 라이브는 FFmpeg `testsrc2` 패턴과 `sine` 음원만 사용합니다. 외부 영상·카메라·마이크·개인 데이터를 입력으로 받지 않습니다. 라이브의 660 Hz 음원은 VOD의 440 Hz와 구별하기 위한 테스트 소리입니다.

## Big Buck Bunny

- 제목: **Big Buck Bunny** (Sunflower 1080p/30fps normal 배포본).
- 출처/귀속: **© 2008 Blender Foundation / www.bigbuckbunny.org**.
- 공식 안내: [Blender 다운로드](https://peach.blender.org/download/), [이용조건](https://peach.blender.org/about/).
- 다운로드 페이지가 연결한 [Blender 공식 미디어 목록](https://download.blender.org/demo/movies/BBB/)의 [1080p 원본 ZIP](https://download.blender.org/demo/movies/BBB/bbb_sunflower_1080p_30fps_normal.mp4.zip).
- 라이선스: [Creative Commons Attribution 3.0 Unported](https://creativecommons.org/licenses/by/3.0/).
- ZIP 크기: 275,524,128바이트(약 263 MiB).
- ZIP SHA-256: `e320fef389ec749117d0c1583945039266a40f25483881c2ff0d33207e62b362`.

원본은 1920×1080 H.264, 약 634.6초이며 stereo MP3와 surround AC-3 트랙을 포함합니다. 이번 재현 스크립트는 **30..60초 구간**을 추출하고, 360p/720p/1080p H.264로 재인코딩하며 첫 stereo 오디오를 AAC 96 kbps로 변환합니다. 각 화질에 2초 HLS MPEG-TS 세그먼트를 만들었습니다. 원작을 가공한 짧은 실험 구간이며 Blender Foundation의 후원·보증을 의미하지 않습니다.

```bash
scripts/prepare_bunny.sh 30 30
```

스크립트는 공식 ZIP만 내려받고 체크섬을 검사합니다. ZIP 내부의 지정된 MP4 한 파일만 안전하게 복사하며 임의 경로를 압축 해제하지 않습니다. 다시 실행하면 원본 캐시를 재사용합니다. 다른 짧은 구간은 시작 초와 길이(최대 120초)를 전달합니다.

원본 ZIP·MP4는 `.local/sources/`, HLS 출력은 `.local/media/bbb/`에 있으며 모두 Git에서 제외합니다. 출처·라이선스·가공 사항은 이 문서와 앱의 Bunny 화면에 표시합니다. Blender 웹사이트의 로고·상표를 프로젝트 디자인에 별도로 사용하지 않습니다.

합성 입력은 네트워크 장애와 라이브 상태를 반복하기에 적합하고, 원작 구간은 실제 움직임·음악/효과음·화질 차이를 살펴보기 위한 입력입니다. 영화에는 대사가 없으므로 음성 대화의 품질 검증으로 취급하지 않습니다.

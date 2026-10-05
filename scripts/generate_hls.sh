#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
duration="${1:-120}"
if ! [[ "$duration" =~ ^[1-9][0-9]*$ ]] || (( duration < 10 || duration > 600 )); then
    echo "Usage: $0 [duration seconds: 10..600]" >&2
    exit 2
fi
command -v ffmpeg >/dev/null
media_dir="$repo_dir/.local/media"
mkdir -p "$media_dir/hls/360p" "$media_dir/hls/720p"

# Only synthetic FFmpeg test patterns and a generated sine wave are used.
ffmpeg -hide_banner -loglevel warning -y \
    -f lavfi -i 'testsrc2=size=1280x720:rate=30' \
    -f lavfi -i 'sine=frequency=440:sample_rate=48000' \
    -t "$duration" -c:v libx264 -preset ultrafast -crf 18 -threads 2 \
    -pix_fmt yuv420p -c:a aac -b:a 96k -movflags +faststart \
    "$media_dir/source.mp4"

ffmpeg -hide_banner -loglevel warning -y -i "$media_dir/source.mp4" \
    -filter_complex '[0:v]split=2[a][b];[a]scale=640:360[low];[b]scale=1280:720[high]' \
    -map '[low]' -map 0:a -map '[high]' -map 0:a \
    -c:v libx264 -preset veryfast -threads 2 -pix_fmt yuv420p \
    -g 60 -keyint_min 60 -sc_threshold 0 \
    -b:v:0 350k -minrate:v:0 350k -maxrate:v:0 350k -bufsize:v:0 700k \
    -b:v:1 1800k -minrate:v:1 1800k -maxrate:v:1 1800k -bufsize:v:1 3600k \
    -x264-params 'nal-hrd=cbr:force-cfr=1' \
    -c:a aac -b:a:0 64k -b:a:1 96k -ac 2 \
    -f hls -hls_time 2 -hls_playlist_type vod \
    -hls_flags independent_segments+temp_file \
    -hls_segment_filename "$media_dir/hls/%v/segment_%03d.ts" \
    -master_pl_name master.m3u8 \
    -var_stream_map 'v:0,a:0,name:360p v:1,a:1,name:720p' \
    "$media_dir/hls/%v/index.m3u8"
printf 'Generated %ss synthetic VOD at .local/media/hls/master.m3u8\n' "$duration"

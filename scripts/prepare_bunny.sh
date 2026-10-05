#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
start="${1:-30}"
duration="${2:-30}"
if ! [[ "$start" =~ ^[0-9]+$ && "$duration" =~ ^[1-9][0-9]*$ ]] || (( duration > 120 )); then
    echo "Usage: $0 [start seconds] [duration seconds: 1..120]" >&2
    exit 2
fi
source_dir="$repo_dir/.local/sources"
base=bbb_sunflower_1080p_30fps_normal.mp4
url="https://download.blender.org/demo/movies/BBB/$base.zip"
mkdir -p "$source_dir"
if [[ ! -f "$source_dir/$base.zip" ]]; then
    curl --fail --location --retry 2 --max-filesize 350000000 \
        "$url" -o "$source_dir/$base.zip.part"
    mv "$source_dir/$base.zip.part" "$source_dir/$base.zip"
fi
python3 - "$source_dir/$base.zip" <<'PY'
import hashlib
import sys
from pathlib import Path
digest = hashlib.sha256()
with Path(sys.argv[1]).open('rb') as archive:
    for block in iter(lambda: archive.read(1024 * 1024), b''):
        digest.update(block)
if digest.hexdigest() != 'e320fef389ec749117d0c1583945039266a40f25483881c2ff0d33207e62b362':
    raise SystemExit('Official archive checksum differs; inspect the source before continuing')
PY
if [[ ! -f "$source_dir/$base" ]]; then
    python3 - "$source_dir/$base.zip" "$source_dir/$base" <<'PY'
import shutil
import sys
import zipfile
from pathlib import Path
archive, destination = map(Path, sys.argv[1:])
with zipfile.ZipFile(archive) as source:
    members = [name for name in source.namelist() if Path(name).name == destination.name]
    if len(members) != 1:
        raise SystemExit('Expected exactly one named MP4 in the official archive')
    temporary = destination.with_suffix('.mp4.part')
    with source.open(members[0]) as original, temporary.open('wb') as output:
        shutil.copyfileobj(original, output)
    temporary.replace(destination)
PY
fi
output_dir="$repo_dir/.local/media/bbb"
mkdir -p "$output_dir/360p" "$output_dir/720p" "$output_dir/1080p"
ffmpeg -hide_banner -loglevel warning -y -ss "$start" -i "$source_dir/$base" -t "$duration" \
    -filter_complex '[0:v]fps=30,split=3[a][b][c];[a]scale=640:360[low];[b]scale=1280:720[mid];[c]scale=1920:1080[high]' \
    -map '[low]' -map 0:a:0 -map '[mid]' -map 0:a:0 -map '[high]' -map 0:a:0 \
    -c:v libx264 -preset veryfast -threads 2 -pix_fmt yuv420p \
    -g 60 -keyint_min 60 -sc_threshold 0 \
    -b:v:0 350k -maxrate:v:0 350k -bufsize:v:0 700k \
    -b:v:1 1800k -maxrate:v:1 1800k -bufsize:v:1 3600k \
    -b:v:2 4000k -maxrate:v:2 4000k -bufsize:v:2 8000k \
    -c:a aac -b:a 96k -ac 2 \
    -f hls -hls_time 2 -hls_playlist_type vod -hls_flags independent_segments+temp_file \
    -hls_segment_filename "$output_dir/%v/segment_%03d.ts" -master_pl_name master.m3u8 \
    -var_stream_map 'v:0,a:0,name:360p v:1,a:1,name:720p v:2,a:2,name:1080p' \
    "$output_dir/%v/index.m3u8"
printf 'Prepared Big Buck Bunny excerpt %s..%ss at .local/media/bbb/master.m3u8\n' "$start" "$((start + duration))"
printf 'Credit: Big Buck Bunny, (c) 2008 Blender Foundation / www.bigbuckbunny.org — CC BY 3.0.\n'

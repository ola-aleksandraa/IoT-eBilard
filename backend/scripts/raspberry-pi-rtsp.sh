
#!/usr/bin/env bash
set -Eeuo pipefail

# Camera configuration
camera_device="${CAMERA_DEVICE:-/dev/video0}"
width="${CAMERA_WIDTH:-1920}"
height="${CAMERA_HEIGHT:-1080}"
fps="${CAMERA_FPS:-30}"

# RTSP configuration
port=8554
stream_path=picam

usage() {
    cat <<EOF
Publish a USB camera as an RTSP stream using MediaMTX and FFmpeg.

Environment variables:
  CAMERA_DEVICE   Camera device (default: /dev/video0)
  CAMERA_WIDTH    Video width (default: ${width})
  CAMERA_HEIGHT   Video height (default: ${height})
  CAMERA_FPS      Frame rate (default: ${fps})

Example:
  CAMERA_WIDTH=1280 CAMERA_HEIGHT=720 CAMERA_FPS=30 ./camera-stream.sh
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

# Validate configuration
for value_name in width height fps; do
    if [[ ! "${!value_name}" =~ ^[0-9]+$ ]] || (( ${!value_name} == 0 )); then
        printf 'Error: %s must be a positive integer.\n' "${value_name^^}" >&2
        exit 2
    fi
done

# Check camera
if [[ ! -e "$camera_device" ]]; then
    printf 'Error: Camera device %s does not exist.\n' "$camera_device" >&2
    exit 1
fi

# Locate MediaMTX
if mediamtx_bin="$(command -v mediamtx)"; then
    :
else
    printf 'Error: mediamtx is required and must be on PATH.\n' >&2
    exit 1
fi

# Locate FFmpeg
if ffmpeg_bin="$(command -v ffmpeg)"; then
    :
else
    printf 'Error: ffmpeg is required and must be on PATH.\n' >&2
    exit 1
fi

# Verify camera tools
if ! command -v v4l2-ctl >/dev/null 2>&1; then
    printf 'Error: v4l2-ctl is required. Install with sudo apt install v4l-utils.\n' >&2
    exit 1
fi

# Check camera capabilities
printf 'Camera: %s\n' "$camera_device"
v4l2-ctl -d "$camera_device" --all >/dev/null

# Process management
mediamtx_pid=""
publisher_pid=""

cleanup() {
    printf '\nStopping camera stream...\n'

    if [[ -n "$publisher_pid" ]]; then
        kill -- "-$publisher_pid" 2>/dev/null || true
        wait "$publisher_pid" 2>/dev/null || true
    fi

    if [[ -n "$mediamtx_pid" ]]; then
        kill "$mediamtx_pid" 2>/dev/null || true
        wait "$mediamtx_pid" 2>/dev/null || true
    fi

    printf 'Stopped.\n'
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Start MediaMTX
printf '\nStarting MediaMTX...\n'

"$mediamtx_bin" &
mediamtx_pid=$!

# Wait for RTSP server
ready=0

for _ in {1..50}; do
    if ! kill -0 "$mediamtx_pid" 2>/dev/null; then
        printf 'Error: MediaMTX stopped unexpectedly.\n' >&2
        exit 1
    fi

    if (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1; then
        ready=1
        break
    fi

    sleep 0.1
done

if (( ! ready )); then
    printf 'Error: MediaMTX did not open port %s.\n' "$port" >&2
    exit 1
fi

stream_url="rtsp://127.0.0.1:${port}/${stream_path}"

# Start FFmpeg USB camera publisher
printf '\nStarting USB camera publisher...\n'

setsid bash -o pipefail -c '
    exec "$1" \
        -hide_banner \
        -loglevel info \
        -f v4l2 \
        -input_format yuyv422 \
        -video_size "${2}x${3}" \
        -framerate "$4" \
        -i "$5" \
        -an \
        -c:v libx264 \
        -preset ultrafast \
        -tune zerolatency \
        -pix_fmt yuv420p \
        -r "$4" \
        -g "$(( $4 * 2 ))" \
        -f rtsp \
        -rtsp_transport tcp \
        "$6"
' _ "$ffmpeg_bin" "$width" "$height" "$fps" "$camera_device" "$stream_url" &

publisher_pid=$!

sleep 2

if ! kill -0 "$publisher_pid" 2>/dev/null; then
    printf 'Error: Camera publisher failed to start.\n' >&2
    exit 1
fi

# Display information
printf '\n========================================\n'
printf '       USB CAMERA RTSP STREAM\n'
printf '========================================\n'

printf 'Camera:     %s\n' "$camera_device"
printf 'Resolution: %sx%s\n' "$width" "$height"
printf 'FPS:        %s\n' "$fps"
printf 'Codec:      H.264\n'
printf 'Encoder:    libx264 ultrafast\n'
printf 'Port:       %s (TCP)\n' "$port"
printf 'Path:       /%s\n' "$stream_path"

printf '\nRTSP URL:\n'
printf '  %s\n' "$stream_url"

addresses="$(hostname -I 2>/dev/null || true)"

if [[ -n "$addresses" ]]; then
    printf '\nNetwork URLs:\n'

    for address in $addresses; do
        printf '  rtsp://%s:%s/%s\n' "$address" "$port" "$stream_path"
    done
fi

printf '\nOpen VLC > Media > Open Network Stream.\n'
printf 'Enter the network RTSP URL and press Play.\n'
printf '\nPress Ctrl+C to stop streaming.\n\n'

# Wait for publisher
if wait "$publisher_pid"; then
    status=0
else
    status=$?
fi

publisher_pid=""

printf 'Camera publisher exited with status %s.\n' "$status" >&2

exit "$status"
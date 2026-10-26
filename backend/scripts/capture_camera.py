#!/usr/bin/env python3
"""Enumerate video devices with OpenCV and capture one still frame.

Device discovery, selection and capture all go through cv2.VideoCapture.
OpenCV has no portable device-name API, so human-readable names come from the
platform camera registry purely for labelling; indices and frames are OpenCV's.

Exposure statistics are printed with every capture because an overexposed
frame silently breaks the detection thresholds downstream.
"""

import argparse
import platform
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

BUILTIN_HINTS = ("facetime", "built-in", "isight", "integrated", "studio display")
# Backends able to enumerate by consecutive index on each platform.
BACKEND = {"Darwin": "CAP_AVFOUNDATION", "Linux": "CAP_V4L2"}.get(platform.system(), "CAP_ANY")


def platform_camera_names():
    """Registry order matches the backend's index order on macOS and Linux."""
    if platform.system() == "Darwin":
        try:
            output = subprocess.run(["system_profiler", "SPCameraDataType"],
                                    capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        names = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.endswith(":") and stripped != "Camera:" and not line.startswith("          "):
                names.append(stripped[:-1])
        return names
    return [path.name for path in sorted(Path("/sys/class/video4linux").glob("video*"))]


def exposure_stats(frame):
    peak = frame.max(axis=2)
    total = peak.size
    return {
        "median": float(np.median(peak)),
        "p99": float(np.percentile(peak, 99)),
        "clipped": float(np.count_nonzero(peak >= 250)) / total,
        "black": float(np.count_nonzero(peak <= 2)) / total,
    }


def describe_exposure(stats):
    if stats["black"] > 0.98:
        return "BLACK FRAME - camera permission denied or lens covered"
    if stats["clipped"] > 0.02 or stats["median"] > 200:
        return "OVEREXPOSED - clipped highlights carry no recoverable detail"
    if stats["median"] < 40:
        return "UNDEREXPOSED"
    return "exposure looks usable"


def open_device(index, width=None, height=None, properties=()):
    capture = cv2.VideoCapture(index, getattr(cv2, BACKEND, cv2.CAP_ANY))
    if not capture.isOpened():
        capture.release()
        return None
    if width and height:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    # Auto-exposure must go off before a manual exposure value is accepted.
    for name, value in properties:
        if not hasattr(cv2, name):
            print("  ! %s unavailable in OpenCV %s" % (name, cv2.__version__))
            continue
        prop = getattr(cv2, name)
        accepted = capture.set(prop, value)
        readback = capture.get(prop)
        print("  %s %s -> requested %s, driver reports %s"
              % ("+" if accepted else "!", name, value, readback))
    return capture


def grab(capture, warmup):
    """Drop the auto-exposure ramp; the last frame is the one worth keeping."""
    frame = None
    for _ in range(max(1, warmup)):
        ok, candidate = capture.read()
        if not ok or candidate is None or candidate.size == 0:
            return frame
        frame = candidate
    return frame


def wait_for_authorization(seconds):
    """AVFoundation answers an access request asynchronously.

    The first open always fails while macOS is still showing its prompt, so
    poll until the user answers instead of forcing a restart of the script.
    """
    deadline = time.monotonic() + seconds
    while True:
        capture = cv2.VideoCapture(0, getattr(cv2, BACKEND, cv2.CAP_ANY))
        opened = capture.isOpened()
        capture.release()
        if opened or time.monotonic() >= deadline:
            return opened
        print("  waiting for camera authorization...")
        time.sleep(2)


def enumerate_devices(probe_limit, warmup):
    names = platform_camera_names()
    devices = []
    for index in range(probe_limit):
        capture = open_device(index)
        if capture is None:
            continue
        try:
            frame = grab(capture, warmup)
            if frame is None:
                continue
            name = names[len(devices)] if len(devices) < len(names) else "device %d" % index
            devices.append({
                "index": index,
                "name": name,
                "builtin": any(hint in name.lower() for hint in BUILTIN_HINTS),
                "resolution": (frame.shape[1], frame.shape[0]),
                "backend": capture.getBackendName(),
                "stats": exposure_stats(frame),
            })
        finally:
            capture.release()
    return devices


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="only enumerate devices")
    parser.add_argument("--index", type=int, help="force a device index")
    parser.add_argument("--builtin", action="store_true",
                        help="use the built-in camera instead of an external one")
    parser.add_argument("--output", default="capture.png", help="output image path")
    parser.add_argument("--width", type=int, help="requested capture width")
    parser.add_argument("--height", type=int, help="requested capture height")
    parser.add_argument("--warmup", type=int, default=15,
                        help="frames discarded before the kept one (default: 15)")
    parser.add_argument("--probe-limit", type=int, default=6, help="highest index probed")
    parser.add_argument("--wait-auth", type=float, default=0,
                        help="seconds to wait for the OS camera permission prompt")
    parser.add_argument("--auto-exposure", type=float,
                        help="CAP_PROP_AUTO_EXPOSURE (V4L2: 0.25 manual, 0.75 auto)")
    parser.add_argument("--exposure", type=float,
                        help="CAP_PROP_EXPOSURE (V4L2: units of 100 us)")
    parser.add_argument("--gain", type=float, help="CAP_PROP_GAIN")
    parser.add_argument("--brightness", type=float, help="CAP_PROP_BRIGHTNESS")
    args = parser.parse_args()

    print("OpenCV %s, backend %s, probing indices 0-%d"
          % (cv2.__version__, BACKEND, args.probe_limit - 1))
    if args.wait_auth > 0:
        wait_for_authorization(args.wait_auth)
    devices = enumerate_devices(args.probe_limit, warmup=3)
    if not devices:
        print("No camera delivered a frame. On macOS grant camera access to the "
              "terminal in System Settings > Privacy & Security > Camera.")
        return 1

    print("\nDetected %d camera(s):" % len(devices))
    for device in devices:
        print("  [%d] %-32s %4dx%-4d  %-12s %s"
              % (device["index"], device["name"], device["resolution"][0],
                 device["resolution"][1], "built-in" if device["builtin"] else "EXTERNAL",
                 device["backend"]))
    if args.list:
        return 0

    if args.index is not None:
        chosen = next((d for d in devices if d["index"] == args.index), None)
        if chosen is None:
            print("\nIndex %d delivered no frame." % args.index)
            return 1
    else:
        wanted = [d for d in devices if d["builtin"] == args.builtin]
        if not wanted:
            kind = "built-in" if args.builtin else "external"
            print("\nNo %s camera found. Pass --index to choose one explicitly." % kind)
            return 1
        chosen = wanted[0]

    print("\nCapturing from [%d] %s" % (chosen["index"], chosen["name"]))
    properties = [(name, value) for name, value in (
        ("CAP_PROP_AUTO_EXPOSURE", args.auto_exposure),
        ("CAP_PROP_EXPOSURE", args.exposure),
        ("CAP_PROP_GAIN", args.gain),
        ("CAP_PROP_BRIGHTNESS", args.brightness),
    ) if value is not None]
    capture = open_device(chosen["index"], args.width, args.height, properties)
    if capture is None:
        print("Device %d could not be reopened." % chosen["index"])
        return 1
    try:
        frame = grab(capture, args.warmup)
    finally:
        capture.release()
    if frame is None:
        print("Capture returned no frame.")
        return 1

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), frame):
        print("Could not write %s" % output)
        return 1

    stats = exposure_stats(frame)
    print("Saved %s (%dx%d)" % (output, frame.shape[1], frame.shape[0]))
    print("  peak median %.1f, p99 %.1f, clipped %.2f%%, black %.2f%%"
          % (stats["median"], stats["p99"], stats["clipped"] * 100, stats["black"] * 100))
    print("  %s" % describe_exposure(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())

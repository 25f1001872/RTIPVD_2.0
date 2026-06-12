"""
Raspberry Pi sender: stream video frames + synchronized GPS to laptop server.

Each packet contains:
- sequence_id
- frame_timestamp_utc
- latest GPS fix (lat/lon/heading/speed/fix)
- JPEG-compressed frame (base64)
"""

import argparse
import time
from pathlib import Path

import cv2
import requests

from src.evidence.gps_tagger import GPSTagger
from src.streaming.packet import FrameTelemetryPacket


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send video+GPS packets to laptop server")
    parser.add_argument("--video-source", required=True, help="Path to video file or camera index")
    parser.add_argument("--server-url", default="http://127.0.0.1:8088/ingest/frame", help="Laptop ingest endpoint")
    parser.add_argument("--target-fps", type=float, default=8.0, help="Send FPS limit")
    parser.add_argument("--jpeg-quality", type=int, default=70, help="JPEG quality (20-95)")
    parser.add_argument("--timeout-sec", type=float, default=5.0, help="HTTP request timeout")
    parser.add_argument("--show-preview", action="store_true", help="Show local preview on Pi")
    return parser.parse_args()


def _open_source(video_source: str) -> cv2.VideoCapture:
    if video_source.isdigit():
        return cv2.VideoCapture(int(video_source))
    return cv2.VideoCapture(video_source)


def main() -> int:
    args = parse_args()

    if not args.video_source.isdigit() and not Path(args.video_source).exists():
        print(f"[ERROR] Video source does not exist: {args.video_source}")
        return 1

    cap = _open_source(args.video_source)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open source: {args.video_source}")
        return 1

    gps = GPSTagger()
    session = requests.Session()

    seq = 0
    send_interval = 0.0 if args.target_fps <= 0 else (1.0 / args.target_fps)
    next_send_t = time.perf_counter()

    print(f"[SENDER] Streaming to: {args.server_url}")
    print(f"[SENDER] Target FPS: {args.target_fps}")
    print(f"[SENDER] GPS ready: {gps.is_ready}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[SENDER] End of source or read failure.")
                break

            now = time.perf_counter()
            if send_interval > 0 and now < next_send_t:
                if args.show_preview:
                    cv2.imshow("Pi Sender Preview", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                continue

            seq += 1
            gps_fix = gps.get_latest()
            packet = FrameTelemetryPacket.from_frame(
                sequence_id=seq,
                frame=frame,
                gps_fix=gps_fix,
                jpeg_quality=args.jpeg_quality,
            )

            try:
                response = session.post(
                    args.server_url,
                    json=packet.to_json(),
                    timeout=args.timeout_sec,
                )
                if not response.ok:
                    print(f"[SENDER] WARN seq={seq} HTTP {response.status_code}: {response.text[:120]}")
                elif seq % 30 == 0:
                    print(f"[SENDER] sent seq={seq} gps_fix={gps_fix.fix}")
            except Exception as exc:
                print(f"[SENDER] WARN seq={seq} send failed: {exc}")

            next_send_t = time.perf_counter() + send_interval

            if args.show_preview:
                cv2.imshow("Pi Sender Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        print("\n[SENDER] Stopped by user.")
    finally:
        cap.release()
        gps.close()
        session.close()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

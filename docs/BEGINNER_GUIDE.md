# RTIPVD Beginner Guide (Pi Streams, Laptop Processes)

This is the updated workflow:

1. Raspberry Pi sends video + GPS over network.
2. Laptop receives packets and runs detection.
3. Laptop computes per-vehicle geospatial coordinates.
4. Illegal/legal parking logic comes next.

## Part A - Hardware wiring

1. Wire NEO-6M to ESP32:
   - NEO VCC -> ESP32 VIN/5V
   - NEO GND -> ESP32 GND
   - NEO TX -> ESP32 GPIO16 (RX2)
   - NEO RX -> ESP32 GPIO17 (TX2)
2. Connect ESP32 USB to Raspberry Pi.
3. Keep GPS antenna outdoors for first fix.

## Part B - Upload project to Raspberry Pi

From laptop PowerShell in repo root:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/raspberry_pi/upload_from_windows.ps1 -PiUser pi -PiHost raspberrypi.local -PiPath ~/RTIPVD
```

## Part C - Setup Raspberry Pi once

SSH into Pi:

```bash
ssh pi@raspberrypi.local
cd ~/RTIPVD
bash deploy/raspberry_pi/setup.sh
```

Put required files on Pi:

1. `weights/best.pt`
2. `data/videos/d1.mp4` (or another source)

## Part D - Start laptop stream server

On laptop PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/laptop/start_stream_server.ps1 -Port 8088
```

Check server health:

```text
http://127.0.0.1:8088/health
```

## Part E - Start Pi sender (video + GPS)

On Pi terminal:

```bash
cd ~/RTIPVD
source .venv/bin/activate

export RTIPVD_VIDEO_SOURCE=data/videos/d1.mp4
export RTIPVD_GPS_ENABLED=true
export RTIPVD_GPS_SOURCE=serial
export RTIPVD_GPS_SERIAL_PORT=/dev/ttyUSB0
export RTIPVD_GPS_BAUD_RATE=9600

export RTIPVD_STREAM_SERVER_URL=http://YOUR_LAPTOP_IP:8088/ingest/frame
export RTIPVD_STREAM_SEND_FPS=8
export RTIPVD_STREAM_JPEG_QUALITY=70
export RTIPVD_STREAM_DEFAULT_HEADING_DEG=0

bash deploy/raspberry_pi/send_stream.sh
```

If your GPS port is not `/dev/ttyUSB0`, find it with:

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

## Part F - Output files generated on laptop

The stream server writes geospatial detections to:

1. `output/results/stream_geocoords.csv`

For offline/local geospatial calculation from video, use:

```bash
python scripts/calculate_vehicle_geocoords.py --video data/videos/d1.mp4 --camera-lat 28.7041 --camera-lon 77.1025 --camera-heading 0 --device cpu
```

## Part G - How GPS is synced with video

Every frame packet includes:

1. Frame timestamp (`frame_timestamp_utc`)
2. GPS timestamp (`gps.timestamp`)
3. GPS coordinates and heading

Laptop sync logic:

1. Uses packet GPS if valid.
2. If missing, uses nearest timestamp fix from GPS sync buffer.
3. If no nearby fix, skips geospatial output for that frame.

## Part H - Troubleshooting

1. Verify Python/modules:

```bash
python scripts/verify_setup.py
```

2. If stream server not reachable from Pi, test:

```bash
curl http://YOUR_LAPTOP_IP:8088/health
```

3. If GPS not available, run sender in mock GPS mode:

```bash
export RTIPVD_GPS_ENABLED=true
export RTIPVD_GPS_SOURCE=mock
bash deploy/raspberry_pi/send_stream.sh
```

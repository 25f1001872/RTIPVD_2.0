# Raspberry Pi Deployment Profile

This folder is for running RTIPVD on Raspberry Pi 4 with GPS and optional backend sync.

## Hardware expected

- Raspberry Pi 4
- ESP32 + NEO-6M GPS module (serial to Pi via USB)
- Optional SIM7600 internet connectivity

## Step-by-step on Raspberry Pi

1. Copy project to Pi (or use `upload_from_windows.ps1` from laptop).
2. On Pi terminal:

```bash
cd ~/RTIPVD
bash deploy/raspberry_pi/setup.sh
```

3. Place required files:
- `weights/best.pt`
- `data/videos/d1.mp4` (or use camera stream)

4. Set env variables (optional quick mode):

```bash
export RTIPVD_GPS_ENABLED=true
export RTIPVD_GPS_SOURCE=serial
export RTIPVD_GPS_SERIAL_PORT=/dev/ttyUSB0
export RTIPVD_BACKEND_ENABLED=true
export RTIPVD_BACKEND_URL=http://YOUR_SERVER_IP:5000/api/violations
```

5. Run pipeline:

```bash
bash deploy/raspberry_pi/run_pi.sh
```

## Notes

- If GPS serial port is different, check with `ls /dev/ttyUSB* /dev/ttyACM*`.
- If backend is not available yet, set `RTIPVD_BACKEND_ENABLED=false`.
- Local SQLite database is always available at `output/db/rtipvd_pi.db`.

## New network mode: send video + GPS to laptop

1. On laptop, start stream server (`deploy/laptop/start_stream_server.ps1`).
2. On Pi, set stream endpoint:

```bash
export RTIPVD_STREAM_SERVER_URL=http://YOUR_LAPTOP_IP:8088/ingest/frame
export RTIPVD_VIDEO_SOURCE=data/videos/d1.mp4
export RTIPVD_STREAM_SEND_FPS=8
export RTIPVD_STREAM_JPEG_QUALITY=70
export RTIPVD_GPS_ENABLED=true
export RTIPVD_GPS_SOURCE=serial
export RTIPVD_GPS_SERIAL_PORT=/dev/ttyUSB0
```

3. Start sender:

```bash
bash deploy/raspberry_pi/send_stream.sh
```

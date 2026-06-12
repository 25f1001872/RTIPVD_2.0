# Streaming Architecture (Raspberry Pi -> Laptop)

This mode makes Raspberry Pi a network sender and the laptop a processing server.

## 1. Data flow

1. Raspberry Pi reads video frames from file/camera.
2. Raspberry Pi reads latest GPS fix from ESP32/NEO-6M.
3. Pi compresses each frame to JPEG and sends packet over HTTP POST.
4. Laptop stream server receives packet and decodes frame.
5. Laptop runs YOLO detection and computes geospatial coordinates for each vehicle.

## 2. Packet schema

Endpoint: `POST /ingest/frame`

```json
{
  "sequence_id": 101,
  "frame_timestamp_utc": "2026-04-14T09:40:11.123+00:00",
  "gps": {
    "latitude": 28.7041,
    "longitude": 77.1025,
    "satellites": 9,
    "heading_deg": 84.2,
    "speed_mps": 2.3,
    "fix": true,
    "source": "serial",
    "timestamp": "2026-04-14T09:40:11+00:00"
  },
  "frame_jpeg_base64": "..."
}
```

## 3. GPS sync strategy

GPS and video are synchronized by timestamps:

1. Every frame packet includes its own frame timestamp.
2. Packet includes the latest GPS fix and GPS timestamp.
3. Laptop stores recent GPS fixes in a sync buffer.
4. If current packet lacks a valid GPS fix, laptop picks nearest fix by timestamp.
5. If no nearby GPS fix exists, frame is processed but geospatial output is skipped.

This method avoids drift and keeps video detections aligned to camera location.

## 4. Geospatial projection

For each detected vehicle:

1. Estimate distance from bounding-box height using pinhole approximation.
2. Convert horizontal pixel offset to bearing offset using camera FOV.
3. Add offset to camera heading.
4. Project destination point from camera lat/lon using bearing+distance.

Output is written to: `output/results/stream_geocoords.csv`

## 5. Start commands

Laptop:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/laptop/start_stream_server.ps1 -Port 8088
```

Raspberry Pi:

```bash
export RTIPVD_STREAM_SERVER_URL=http://YOUR_LAPTOP_IP:8088/ingest/frame
bash deploy/raspberry_pi/send_stream.sh
```

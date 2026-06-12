# Laptop Deployment Profile

This folder is for quick algorithm testing on your Windows laptop.

## What this profile does

- Uses GPU (`cuda:0`) if available
- Uses mock GPS coordinates so you can test without hardware
- Stores violations in local SQLite (`output/db/rtipvd_laptop.db`)

## Step-by-step

1. Copy your model to `weights/best.pt`
2. Copy your video to `data/videos/d1.mp4`
3. Start backend dashboard in one terminal:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/laptop/start_backend.ps1
```

4. Start detection pipeline in second terminal:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/laptop/run_laptop.ps1
```

5. Open dashboard in browser:

```text
http://127.0.0.1:5000/dashboard
```

## Optional

Use mock OCR for very fast tests:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/laptop/run_laptop.ps1 -UseMockOcr
```

## New network mode (Pi streams to laptop)

Start the laptop stream processing server:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/laptop/start_stream_server.ps1 -Port 8088
```

Health check URL:

```text
http://127.0.0.1:8088/health
```

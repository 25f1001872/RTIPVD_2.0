Raspberry Pi Sender Bundle

This folder contains the minimum files required for sender-only mode:
- Raspberry Pi sends video + GPS
- Laptop does detection and geospatial processing

How to upload this bundle from Windows PowerShell:

1) Move to project root:
   cd C:\Users\rawat\OneDrive\Documents\GitHub\RTIPVD

2) Upload to Pi:
   scp -r raspberry_pi_sender_bundle pi@raspberrypi.local:~/

3) SSH into Pi and setup:
   ssh pi@raspberrypi.local
   cd ~/raspberry_pi_sender_bundle
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install numpy opencv-python requests pyserial

4) Set stream and GPS variables (example):
   export RTIPVD_VIDEO_SOURCE=data/videos/d1.mp4
   export RTIPVD_GPS_ENABLED=true
   export RTIPVD_GPS_SOURCE=serial
   export RTIPVD_GPS_SERIAL_PORT=/dev/ttyUSB0
   export RTIPVD_GPS_BAUD_RATE=9600
   export RTIPVD_STREAM_SERVER_URL=http://YOUR_LAPTOP_IP:8088/ingest/frame

5) Start sender:
   bash deploy/raspberry_pi/send_stream.sh

If you only want to test transport first, set:
   export RTIPVD_GPS_SOURCE=mock

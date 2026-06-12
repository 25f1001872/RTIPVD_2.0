# Model Weights

This directory contains the trained YOLO model weights.

## Required Files

| File | Description | Size |
|------|-------------|------|
| `best.pt` | Custom YOLOv8 trained weights | ~20-50 MB |

## How to Get the Weights

### Option 1: From Team Drive
Download `best.pt` from our shared drive and place it here.

### Option 2: Train Your Own
```bash
yolo train model=yolov8n.pt data=data/dataset/data.yaml epochs=100 imgsz=640
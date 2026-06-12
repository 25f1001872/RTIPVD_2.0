# 2. Create all the directories and subdirectories
mkdir -p src/{detection,ego_motion,analyzer,ocr,preprocessing,evidence,database/migrations,visualization,utils}
mkdir -p config weights data/{videos,sample_frames,dataset/{images,labels}}
mkdir -p output/{violations/{screenshots,logs},results,db}
mkdir -p dashboard/{backend,frontend,templates} deploy/{jetson_nano,raspberry_pi,docker}
mkdir -p docs presentations/assets tests scripts

# 3. Create all files inside the 'src' directory
touch src/__init__.py
touch src/detection/{__init__.py,vehicle_detector.py,vehicle_tracker.py}
touch src/ego_motion/{__init__.py,lane_detector.py,motion_estimator.py}
touch src/analyzer/{__init__.py,parking_analyzer.py,calibrator.py}
touch src/ocr/{__init__.py,plate_detector.py,plate_reader.py}
touch src/preprocessing/{__init__.py,frame_processor.py}
touch src/evidence/{__init__.py,screenshot_capture.py,gps_tagger.py,map_overlay.py}
touch src/database/{__init__.py,db_manager.py,models.py,migrations/init_schema.sql}
touch src/visualization/{__init__.py,frame_renderer.py,stats_overlay.py}
touch src/utils/{__init__.py,logger.py,timer.py,validators.py}

# 4. Create config and weights files
touch config/{config.py,bytetrack.yaml,config.example.py}
touch weights/{best.pt,.gitkeep,README.md}

# 5. Create data and output files
touch data/videos/{dashcam_day.mp4,dashcam_night.mp4,drone_footage.mp4,.gitkeep}
touch data/sample_frames/.gitkeep
touch data/dataset/data.yaml
touch output/violations/screenshots/.gitkeep
touch output/violations/logs/.gitkeep
touch output/results/.gitkeep
touch output/db/{rtipvd.db,.gitkeep}

# 6. Create dashboard and deployment files
touch dashboard/backend/{app.py,routes.py,requirements.txt}
touch dashboard/frontend/{index.html,styles.css,app.js}
touch dashboard/templates/base.html
touch deploy/jetson_nano/{setup.sh,optimize_model.py}
touch deploy/raspberry_pi/setup.sh
touch deploy/docker/{Dockerfile,docker-compose.yml}

# 7. Create documentation, presentations, tests, and scripts
touch docs/{architecture.svg,demo_pipeline.svg,gaps_radar.svg,parking_detection_explanation.md,parking_detection_explanation.pdf,api_reference.md}
touch presentations/{IITR_template.pptx,mid_eval_presentation.pptx}
touch presentations/assets/{newspaper_cutout1.png,traffic_photo.jpg}
touch tests/{__init__.py,test_detection.py,test_ego_motion.py,test_parking_analyzer.py,test_plate_reader.py,test_database.py}
touch scripts/{download_weights.py,convert_model.py,generate_report.py}

# 8. Create root-level files
touch main.py requirements.txt .gitignore .env.example README.md LICENSE

echo "RTIPVD folder structure successfully created!"

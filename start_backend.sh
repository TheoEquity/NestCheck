#!/bin/bash
# /workspace/NestCheck/start_backend.sh
# Backend auto-restart script

LOG_DIR="logs"
mkdir -p $LOG_DIR

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backend..."
    python3 main.py --serve-only 2>&1 | tee -a $LOG_DIR/backend_daemon.log
    
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backend exited with code $EXIT_CODE. Restarting in 3s..."
    
    # Graceful restart delay
    sleep 3
done

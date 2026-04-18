#!/bin/bash
cd /root/risk_system
source myenv/bin/activate
nohup python http_api.py > logs/api.log 2>&1 &
echo $! > api.pid
echo "服务已启动，PID: $(cat api.pid)"

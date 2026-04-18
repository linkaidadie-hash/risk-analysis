#!/bin/bash
set -e
cd /root/risk_system
python3 -m pip install -r requirements.txt
mkdir -p logs data/uploads templates
python3 http_api.py

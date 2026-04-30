#!/bin/bash
cd /home/user/daily-market-brief
python3 main.py >> /home/user/daily-market-brief/cron.log 2>&1

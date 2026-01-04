#!/bin/bash
# Simple script to check memory usage of python processes
echo "Timestamp,RSS_MB"
while true; do
    RSS=$(ps -e -o rss,comm | grep python | awk '{s+=$1} END {print int(s/1024)}')
    echo "$(date '+%Y-%m-%d %H:%M:%S'),${RSS:-0}"
    sleep 2
done

#!/bin/bash
# View logs from all services or specific service

if [ -z "$1" ]; then
    echo "Following logs from all services..."
    echo "Press Ctrl+C to stop"
    echo ""
    docker compose logs -f
else
    echo "Following logs from $1..."
    echo "Press Ctrl+C to stop"
    echo ""
    docker compose logs -f "$1"
fi

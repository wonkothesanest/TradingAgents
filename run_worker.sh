#!/bin/bash
# Convenience script to run the Celery worker

set -e

echo "Starting TradingAgents Celery worker..."
echo "Worker will consume tasks from Redis: redis://localhost:6379/0"
echo "Concurrency: 2 workers (configurable with --concurrency)"
echo "Time limit: 1800 seconds (30 minutes)"
echo "Soft time limit: 1500 seconds (25 minutes)"
echo ""
echo "Press Ctrl+C to stop the worker"
echo ""

celery -A trading_api.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --time-limit=1800 \
    --soft-time-limit=1500 \
    --max-tasks-per-child=50

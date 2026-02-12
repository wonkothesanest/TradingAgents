#!/bin/bash
# Convenience script to run the FastAPI server

set -e

echo "Starting TradingAgents API server..."
echo "API will be available at: http://localhost:8000"
echo "API docs (Swagger UI): http://localhost:8000/docs"
echo "API docs (ReDoc): http://localhost:8000/redoc"
echo ""

uvicorn trading_api.main:app --host 0.0.0.0 --port 8000 --reload

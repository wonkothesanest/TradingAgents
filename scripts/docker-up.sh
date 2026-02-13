#!/bin/bash
# Start all services

set -e

echo "Starting TradingAgents services with Docker Compose..."
echo ""
echo "Services will be available at:"
echo "  API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Ollama: http://localhost:11434"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found"
    echo "Copy .env.example to .env and fill in your API keys:"
    echo "  cp .env.example .env"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Start services
docker compose up --build -d

echo ""
echo "✅ Services started!"
echo ""
echo "Check status: docker compose ps"
echo "View logs: docker compose logs -f"
echo "Stop services: docker compose down"

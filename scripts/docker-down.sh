#!/bin/bash
# Stop all services

set -e

echo "Stopping TradingAgents services..."
docker compose down

echo ""
echo "✅ Services stopped"
echo ""
echo "To remove volumes (WARNING: deletes data):"
echo "  docker compose down -v"

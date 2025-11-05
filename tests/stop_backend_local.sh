#!/bin/bash
# stop_backend_local.sh
# Stop AYNI Backend Local Environment
# Last Updated: 2025-11-05 (Task 008)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🛑 Stopping AYNI Backend Local Environment..."
echo "================================================"

cd "$PROJECT_ROOT"

# Stop all services
echo "Stopping services: db, redis, backend, celery, celery-beat, flower"
docker-compose stop db redis backend celery celery-beat flower

echo ""
echo "✅ All backend services stopped"
echo ""
echo "📊 Remaining containers:"
docker-compose ps
echo ""
echo "💡 To completely remove containers and volumes:"
echo "   docker-compose down -v"
echo ""

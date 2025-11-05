#!/bin/bash
# start_backend_local.sh
# Initialize AYNI Backend Local Environment
# Last Updated: 2025-11-05 (Task 008)
# Services: PostgreSQL, Redis, Django, Celery, Flower

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 Starting AYNI Backend Local Environment..."
echo "================================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Navigate to project root
cd "$PROJECT_ROOT"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. Copying from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ Created .env from .env.example"
    else
        echo "❌ Error: .env.example not found. Cannot proceed."
        exit 1
    fi
fi

echo ""
echo "📦 Starting services with Docker Compose..."
echo "Services: db, redis, backend, celery, celery-beat, flower"
echo ""

# Start all backend services
docker-compose up -d db redis backend celery celery-beat flower

# Wait for services to be healthy
echo ""
echo "⏳ Waiting for services to be healthy..."
echo ""

# Wait for PostgreSQL
echo "  Checking PostgreSQL..."
timeout 30 bash -c 'until docker-compose exec -T db pg_isready -U ayni_user > /dev/null 2>&1; do sleep 1; done' || {
    echo "❌ PostgreSQL failed to start"
    exit 1
}
echo "  ✅ PostgreSQL ready"

# Wait for Redis
echo "  Checking Redis..."
timeout 30 bash -c 'until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do sleep 1; done' || {
    echo "❌ Redis failed to start"
    exit 1
}
echo "  ✅ Redis ready"

# Wait for Django (check if port 8000 is responding)
echo "  Checking Django..."
timeout 60 bash -c 'until curl -s http://localhost:8000/admin/ > /dev/null 2>&1; do sleep 2; done' || {
    echo "❌ Django failed to start"
    exit 1
}
echo "  ✅ Django ready"

# Wait for Flower (check if port 5555 is responding)
echo "  Checking Flower..."
timeout 30 bash -c 'until curl -s http://localhost:5555 > /dev/null 2>&1; do sleep 2; done' || {
    echo "❌ Flower failed to start"
    exit 1
}
echo "  ✅ Flower ready"

# Check Celery worker is running
echo "  Checking Celery worker..."
if docker-compose ps celery | grep -q "Up"; then
    echo "  ✅ Celery worker running"
else
    echo "  ⚠️  Warning: Celery worker may not be running"
fi

echo ""
echo "================================================"
echo "✅ All backend services started successfully!"
echo "================================================"
echo ""
echo "🌐 Access Points:"
echo "  - Django API:     http://localhost:8000"
echo "  - Django Admin:   http://localhost:8000/admin/"
echo "  - API Docs:       http://localhost:8000/api/docs/"
echo "  - Flower:         http://localhost:5555"
echo ""
echo "📊 Service Status:"
docker-compose ps
echo ""
echo "📝 View logs:"
echo "  - All services:   docker-compose logs -f"
echo "  - Django:         docker-compose logs -f backend"
echo "  - Celery:         docker-compose logs -f celery"
echo "  - Flower:         docker-compose logs -f flower"
echo ""
echo "🛑 Stop services:  ./tests/stop_backend_local.sh"
echo ""

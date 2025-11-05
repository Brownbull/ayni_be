@echo off
REM start_backend_local.bat
REM Initialize AYNI Backend Local Environment
REM Last Updated: 2025-11-05 (Task 008)
REM Services: PostgreSQL, Redis, Django, Celery, Flower

echo 🚀 Starting AYNI Backend Local Environment...
echo ================================================

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Error: Docker is not running. Please start Docker Desktop.
    exit /b 1
)

REM Navigate to project root
cd /d "%~dp0.."

REM Check if .env file exists
if not exist ".env" (
    echo ⚠️  Warning: .env file not found. Copying from .env.example...
    if exist ".env.example" (
        copy .env.example .env
        echo ✅ Created .env from .env.example
    ) else (
        echo ❌ Error: .env.example not found. Cannot proceed.
        exit /b 1
    )
)

echo.
echo 📦 Starting services with Docker Compose...
echo Services: db, redis, backend, celery, celery-beat, flower
echo.

REM Start all backend services
docker-compose up -d db redis backend celery celery-beat flower

echo.
echo ⏳ Waiting for services to be healthy...
echo.

REM Wait for services (simplified for Windows)
timeout /t 15 /nobreak >nul

echo.
echo ================================================
echo ✅ All backend services started!
echo ================================================
echo.
echo 🌐 Access Points:
echo   - Django API:     http://localhost:8000
echo   - Django Admin:   http://localhost:8000/admin/
echo   - API Docs:       http://localhost:8000/api/docs/
echo   - Flower:         http://localhost:5555
echo.
echo 📊 Service Status:
docker-compose ps
echo.
echo 🛑 Stop services:  tests\stop_backend_local.bat
echo.

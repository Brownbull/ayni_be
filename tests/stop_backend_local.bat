@echo off
REM stop_backend_local.bat
REM Stop AYNI Backend Local Environment
REM Last Updated: 2025-11-05 (Task 008)

echo 🛑 Stopping AYNI Backend Local Environment...
echo ================================================

cd /d "%~dp0.."

echo Stopping services: db, redis, backend, celery, celery-beat, flower
docker-compose stop db redis backend celery celery-beat flower

echo.
echo ✅ All backend services stopped
echo.
echo 📊 Remaining containers:
docker-compose ps
echo.
echo 💡 To completely remove containers and volumes:
echo    docker-compose down -v
echo.

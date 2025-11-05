# AYNI Backend

Analytics platform backend for Chilean PYMEs.

## Tech Stack

- **Framework:** Django 5.0 + Django REST Framework
- **Database:** PostgreSQL 15
- **Cache/Queue:** Redis 7
- **Task Queue:** Celery
- **WebSocket:** Django Channels
- **Authentication:** JWT (Simple JWT)

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15 (if running locally)
- Redis 7 (if running locally)

### Setup with Docker (Recommended)

1. **Clone and navigate:**
   ```bash
   cd C:/Projects/play/ayni_be
   ```

2. **Create .env file:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Build and run:**
   ```bash
   docker-compose up --build
   ```

4. **Access:**
   - API: http://localhost:8000
   - Admin: http://localhost:8000/admin
   - API Docs: http://localhost:8000/api/docs/

### Setup without Docker

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup database:**
   ```bash
   # Create PostgreSQL database
   createdb ayni_db
   ```

4. **Create .env file:**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

5. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

6. **Create superuser:**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run development server:**
   ```bash
   python manage.py runserver
   ```

8. **Run Celery (separate terminal):**
   ```bash
   celery -A config worker -l info
   ```

## Project Structure

```
ayni_be/
├── config/              # Django project configuration
│   ├── settings.py      # Django settings
│   ├── urls.py          # Root URL configuration
│   ├── wsgi.py          # WSGI entry point
│   ├── asgi.py          # ASGI entry point (WebSocket)
│   └── celery.py        # Celery configuration
├── apps/                # Django applications
│   ├── authentication/  # User auth & JWT
│   ├── companies/       # Company management
│   ├── processing/      # Data upload & processing
│   └── analytics/       # Analytics API
├── media/               # Uploaded files
├── staticfiles/         # Static files (production)
├── requirements.txt     # Python dependencies
├── manage.py            # Django management script
├── Dockerfile           # Docker image definition
├── docker-compose.yml   # Multi-container orchestration
├── pytest.ini           # Test configuration
└── README.md            # This file
```

## Development

### Running Tests

```bash
# All tests
pytest

# Specific app
pytest apps/authentication

# With coverage report
pytest --cov=apps --cov-report=html
```

### Code Quality

```bash
# Format code
black apps/

# Lint code
flake8 apps/

# Type checking
mypy apps/
```

### Database Migrations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migrations
python manage.py showmigrations
```

### Django Shell

```bash
python manage.py shell
# Or with IPython
python manage.py shell_plus --ipython
```

## API Documentation

- **Swagger UI:** http://localhost:8000/api/docs/
- **OpenAPI Schema:** http://localhost:8000/api/schema/

## Environment Variables

See `.env.example` for all available environment variables.

## Deployment

### Production Checklist

- [ ] Set `DEBUG=False`
- [ ] Set strong `SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Setup PostgreSQL database
- [ ] Setup Redis instance
- [ ] Configure `SENTRY_DSN` for error tracking
- [ ] Setup SSL/TLS certificates
- [ ] Configure CORS origins
- [ ] Run `collectstatic`
- [ ] Setup Celery workers
- [ ] Configure backup strategy

## Ports

- **Django:** 8000
- **PostgreSQL:** 5432
- **Redis:** 6379

## License

Proprietary - AYNI Platform

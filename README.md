# AssessApp

A Django-based assessment platform for tracking student progress against SEND/EHCP frameworks, with evidence capture, AI-assisted observations and Arbor MIS integration.

## Features

- Personalised assessment frameworks per student
- Evidence capture (photo, video, audio, text) with optional face blur
- AI-assisted observation tagging (configurable provider)
- Arbor MIS integration (read-only, GraphQL)
- Microsoft 365 / Entra ID SSO via django-allauth
- Reports & PDF export
- HTMX-driven UI on Django templates

## Tech Stack

- Django 5 / Python 3.12
- PostgreSQL 16
- Gunicorn + Nginx (in production)
- Docker Compose for deployment

## Quick Start (Docker)

1. Clone the repo:
   ```bash
   git clone https://github.com/DPlazma/assessapp.git
   cd assessapp
   ```

2. Copy the example env file and fill it in:
   ```bash
   cp .env.example .env
   # edit .env with real values (see below)
   ```

3. Build and start:
   ```bash
   docker compose up -d --build
   ```

4. Create a superuser:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

5. Open http://localhost in your browser.

## Environment Variables

See [.env.example](.env.example) for the full list. At minimum you must set:

- `DJANGO_SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DJANGO_ALLOWED_HOSTS` — comma-separated hostnames the app will respond to
- `POSTGRES_PASSWORD` — strong password for the database
- `MS_CLIENT_ID` / `MS_CLIENT_SECRET` / `MS_TENANT_ID` — for Microsoft 365 SSO (optional in dev)

For production, also set `DJANGO_DEBUG=False`.

## Production Notes

- Set `DJANGO_DEBUG=False` and a real `DJANGO_SECRET_KEY`.
- Configure `DJANGO_ALLOWED_HOSTS` to your real domain(s).
- Put a TLS-terminating reverse proxy in front (or extend the bundled `nginx` service with certbot).
- Take regular `pg_dump` backups of the `db` service.

## Development

Without Docker:

```bash
python -m venv .venv
. .venv/Scripts/activate          # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

## Repository Layout

```
config/         Django settings (base / dev / prod) + ASGI/WSGI
core/           Shared models, AI/Arbor settings, dashboard
students/       Student records
staff/          Staff records and permissions
assessments/    Frameworks, areas, sub-areas, assignments
evidence/       Evidence capture & processing (face blur, transcripts)
reports/        Report generation
notifications/  In-app notifications
templates/      Django templates
static/         Source static assets
nginx/          Nginx site config used by docker-compose
scratch/        One-off probe / debug scripts (gitignored)
```

## License

MIT — see [LICENSE](LICENSE).

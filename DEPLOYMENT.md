# Deploying to Render

This repository includes a Render Blueprint in `render.yaml`. In Render, create a
Blueprint from the GitHub repository and use the existing PostgreSQL database's
internal connection URL when prompted for `DATABASE_URL`. Do not create a new
database if you need to keep data from an existing deployment.

The Blueprint installs dependencies, collects static files, applies migrations,
and starts the Django app with Gunicorn. It generates `SECRET_KEY` and sets
`DEBUG=False`. Render supplies the service hostname; custom domains can be added
to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` as environment variables.

For an existing Render web service, use these commands from the backend
directory:

- Build: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate --noinput`
- Start: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`

For local development, copy `.env.example` to `.env`. The settings load that
file locally, use the `DB_*` values for PostgreSQL when `DB_HOST` is set, and
otherwise use the local SQLite database. Never commit `.env`; configure
production secrets and database URLs in Render's environment settings.

Uploaded menu images are stored under `media/`. Render's default web-service
filesystem is ephemeral, so uploads may be lost on redeploy or restart. Use a
persistent disk or object storage before relying on uploaded images in production.

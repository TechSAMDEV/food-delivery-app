# Deploying to Render

This repository includes a Render Blueprint in `render.yaml`. In Render, create a
Blueprint from the GitHub repository and use the existing PostgreSQL database's
internal connection URL when prompted for `DATABASE_URL`. Do not create a new
database if you need to keep data from an existing deployment.

The Blueprint installs dependencies, collects static files, applies migrations,
and starts the Django app with Gunicorn. It generates `SECRET_KEY` and sets
`DEBUG=False`. Render supplies the service hostname; custom domains can be added
to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` as environment variables.
Add `FLUTTERWAVE_SECRET_KEY` and `FLUTTERWAVE_WEBHOOK_SECRET` in the Render
service environment before accepting online payments. Configure the Flutterwave
webhook URL as `https://<your-render-host>/payments/flutterwave/webhook/` and use
the same webhook secret hash in Flutterwave and Render.

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

Administrators assign delivery orders from **Django admin → Store → Orders** by
editing the assigned rider field. Riders sign in to the customer-facing site and
open **Rider deliveries** to view assigned jobs and confirm delivery. Customers
can use **My orders** to review previous orders and follow status updates.

Checkout redirects customers to Flutterwave. The app verifies each transaction
server-side before moving an order into kitchen preparation. Set the Flutterwave
secret key and webhook secret only in Render's environment settings or in the
local `.env` file; never commit them.

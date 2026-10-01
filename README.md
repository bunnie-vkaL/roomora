# ROOMORA

ROOMORA is a Vietnamese, mobile-first MVP for finding compatible roommates in Hanoi. It compares lifestyle preferences before people choose to connect.

## Run locally

Requires Python 3.12+ and SQLite (included with Python).

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000`. Create regular test accounts through the registration page. `seed_demo` makes 40 records labeled as synthetic demo data. They appear only in local development to make the full journey testable, and are excluded whenever `DEBUG=False`.

## Commands

```bash
python manage.py test
python manage.py check --deploy
python manage.py seed_demo
```

Set `SECRET_KEY`, `DEBUG=False`, and `ALLOWED_HOSTS` in the environment before any deployment. Password reset links print to the server console in this local MVP.

## Pilot workflow

Staff can view aggregate pilot outcomes and download a CSV at `/staff/pilot/`. The study keeps contact information and raw questionnaire answers out of its export.

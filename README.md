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

## Lifestyle matching v2026.2

The onboarding survey uses the 16 criteria A1-F2 from the supplied ROOMORA Lifestyle Survey & Compatibility Score v1.0. `core/constants.py` holds the questions and their 0.92 total weight. `core/scoring.py` applies the document's ordinal and categorical similarities, specified lifestyle exclusion pairs, tier adjustment, penalties, budget alignment bonus, and piecewise calibration anchors. The four behavior indicators S1-S4 (0.08 total weight) use the document's neutral 0.5 missing-data value because this MVP does not measure them yet. The displayed percentage is an estimated compatibility index, not a measured probability of staying together for three months.

The source gives tier factors but does not map tiers to criteria, so the assignment in `core/scoring.py` is provisional. It also requires data the MVP does not collect for several H1-H6 gates and evidence bonuses; those rules are not inferred from missing data. The location gate uses the app's shared district selections, and the budget gate uses overlapping accepted ranges. Results are limited to ten profiles; the density-dependent minimum score needs geospatial density data before it can follow the document. The calibration anchors and weights need validation with real outcomes before the score can be interpreted statistically.

Migration `0005` unpublishes existing profiles because the old 19-answer format cannot reliably be converted to the new 16 questions. Those users must answer the new survey before appearing in matching again. For local demo profiles, run `python manage.py seed_demo` after migration to refresh their answers and republish them.

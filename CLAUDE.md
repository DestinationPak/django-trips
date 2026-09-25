# CLAUDE.md

`django-trips` is a reusable Django app published on PyPI: trips, schedules, bookings, hosts and locations, as models, querysets, business rules (`services.py`) and admin. The app lives in `src/django_trips/`; `devsite/` is a dev-only project shell.

This file holds only what every session needs. Details live in `docs/development/`; read the matching file before working in that area.

## Commands

All development runs in Docker. `make dev.up` (SQLite by default), `make shell`, `make update_db`, `make random_trips`, `make test`. Lint with `python run_lint.py`. Inside the container, `pytest path::Class::test` runs one test.

## Git workflow

`main` is the base branch. Never commit to `main`: branch off the latest `main`, push, open a PR. Once a branch's PR merges, cut a fresh branch and cherry-pick anything unlanded. The repo lives at `DestinationPak/django-trips`, but the local remote may still point at the old URL, so pass `-R DestinationPak/django-trips` to `gh`.

## Rules that fail silently

- **No API here.** Never add a view, serializer or `urls.py`. A new rule goes in `services.py` (writes) or a queryset in `managers.py` (reads), raising `ValidationError` with a dict keyed by field.
- **Location is swappable.** Declare FKs with `swapper.get_model_name("django_trips", "Location")` and reach the model through `get_location_model()`, never by importing `Location`.
- **Tests run on SQLite, not MySQL.** `select_for_update()` is ignored (assert the lock is requested) and there are no unsigned columns (floor any subtraction on a counter at zero). `make test` must keep its `-e DJANGO_SETTINGS_MODULE=settings.test`, or tests silently hit MySQL.
- **Tests:** `django.test.TestCase` classes, fixtures from `django_trips/tests/factories.py` instead of `objects.create()`. `TripScheduleFactory` picks a random status, so pin `PUBLISHED` for booking tests.
- **Every change ships to PyPI.** Check public import paths and packaging against a real install and `python -m build` + `twine check`. The version comes from the git tag: tag the merge commit with no `v` prefix, and pushing it publishes.
- **Keep `include-package-data` off** in `pyproject.toml`, or every tracked file lands in the wheel.
- This repo is public: never reference a private consuming project's code or paths.

## Where to read more

| Working on | Read |
|---|---|
| Commands, the `make test` settings trap, MySQL opt-in, seeding, lint | `docs/development/setup.md` |
| Domain model, swappable Location, services and querysets | `docs/development/architecture.md` |
| `pyproject.toml`, versioning, tags, releases | `docs/development/packaging.md` |
| Public usage, custom Location model, pricing model | `README.md` |

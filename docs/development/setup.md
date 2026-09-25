# Local development

All development happens inside Docker; there is no supported bare-metal workflow. The importable app is `src/django_trips/`; `devsite/` is a throwaway Django project shell (`urls.py`/`wsgi.py`/`asgi.py`) used only for local dev and not part of the published package.

## Commands

```bash
make build          # docker compose build (destroys existing containers first)
make dev.up         # start web (SQLite by default, see Settings below for MySQL)
make shell          # a shell inside the web container
make update_db      # run migrations
make random_trips   # seed random trips (generate_trips --batch_size=100)
make test           # run pytest on in-memory SQLite
make stop / make destroy  # stop / tear down containers (destroy removes volumes)
make logs           # tail web container logs
```

Run a single test inside the container (`make shell`):

```bash
pytest django_trips/tests/test_services.py
pytest django_trips/tests/test_services.py::CreateTripBookingTestCase::test_adds_the_party_to_booked_seats
```

## Why `make test` passes `-e DJANGO_SETTINGS_MODULE`

`make test` runs `docker compose run --rm --no-deps -e DJANGO_SETTINGS_MODULE=settings.test web pytest`. The `web` service sets `DJANGO_SETTINGS_MODULE=settings.common` for the whole container, and pytest-django only uses `pytest.ini`'s value as a fallback (`os.environ.setdefault`). Without the explicit `-e`, tests silently run against real MySQL, and `--no-deps` (skip starting the database) becomes unsafe.

`settings.test` imports `settings.common` and swaps `DATABASES` to in-memory SQLite. With `--no-migrations`, tests build the schema straight from models, so tests pick up model changes without a migration. Still create the migration for real deployments.

SQLite differs from MySQL in ways tests won't catch: it ignores `select_for_update()` (so a lock is tested by asserting it is requested), and it has no unsigned columns (so a subtraction that goes below zero only fails on MySQL).

## Tests

- Write tests as `django.test.TestCase` subclasses, not bare `@pytest.mark.django_db` functions.
- Build fixtures with `django_trips/tests/factories.py` (`HostFactory`, `TripFactory`, …), not `Model.objects.create(...)`. A raw `create()` is fine when the test is about model/manager mechanics.
- `TripScheduleFactory` picks a random status, so booking tests must pin `PUBLISHED`.

## Linting

`python run_lint.py` runs pylint over `django_trips/` and fails below the `THRESHOLD` in `run_lint.py`. pep8speaks enforces a 120-character line length on PR diffs (`.pep8speaks.yml`). `.pylintrc` ignores `tests.py`, `urls.py` and migrations.

## Settings

`settings/common.py` is the real settings module (Docker sets `DJANGO_SETTINGS_MODULE=settings.common`); `settings/test.py` re-exports it with SQLite.

`DATABASES` reads `DATABASE_ENGINE`, defaulting to SQLite, the same pattern django-oscar and wagtail use. MySQL is opt-in and needs both:

- the compose profile: `docker compose --profile mysql up` (the `database` service has `profiles: [mysql]`), and
- `DATABASE_ENGINE=django.db.backends.mysql` in `.env`.

`mysqlclient` is installed by its own `RUN pip install` in the `Dockerfile`, not as a project dependency, so it stays out of the dependency graph and Dependabot; it's dev-only.

`web` has no `depends_on: database` health gate (Compose can't depend on a profile-gated service that isn't active). On a fresh MySQL opt-in, `web`'s first `migrate` can race MySQL's startup and fail once; `restart: unless-stopped` retries it within seconds.

## Seeding

`generate_trips` (`django_trips/management/commands/generate_trips.py`) seeds fake trips, hosts and locations, driven by the `TRIP_*` settings in `settings/common.py` (`TRIP_DESTINATIONS`, `TRIP_HOSTS`, `TRIP_LOCATIONS_BY_REGION`, …) unless the project sets `USE_DEFAULT_TRIPS=True`. When adding seed settings, update `settings/common.py` and the README's "Generate random trips" section together.

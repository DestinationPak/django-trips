# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`django-trips` is a reusable Django app (published as a pip package, see `pyproject.toml`) for trips, schedules,
bookings, hosts, and locations: models, querysets, business rules (`services.py`) and admin. It's the core trips
domain behind the [DestinationPak](https://destinationpak.com) platform. It ships no API, views or URLs (the DRF
API was removed in 2.0.0): each consumer builds its own endpoints on the services and querysets. Never add an
endpoint, serializer or `urls.py` back; a new rule goes in `services.py` or a queryset.

The importable app lives at `src/django_trips/` (`src/` layout - see "Packaging" below for why). `devsite/` is a
separate, throwaway Django *project* shell used only for local dev (`urls.py`/`wsgi.py`/`asgi.py`) - deliberately
named nothing like `django_trips` so the two can't be confused with each other or with the published package.

## Common commands

All development happens inside Docker; there is no supported bare-metal workflow.

```bash
make build          # docker compose build (destroys existing containers first)
make dev.up          # start web (SQLite by default - see "Settings" below for the MySQL opt-in)
make shell           # attach a shell inside the web container (django-shell alias)
make update_db        # run migrations
make random_trips      # seed random trips (generate_trips --batch_size=100)
make test            # docker compose run --rm --no-deps -e DJANGO_SETTINGS_MODULE=settings.test web pytest
make stop / make destroy  # stop / tear down containers (destroy removes volumes too)
make logs            # tail web container logs
```

`make test` explicitly overrides `DJANGO_SETTINGS_MODULE` and skips the `database` dependency -
`settings/test.py` swaps in an in-memory SQLite `DATABASES`, but `docker-compose.yml`'s `web`
service sets `DJANGO_SETTINGS_MODULE=settings.common` as a container-wide environment variable,
which pytest-django only ever uses as a fallback (`os.environ.setdefault`, never overriding an
already-set var) - so without the explicit `-e` override, `pytest.ini`'s own
`DJANGO_SETTINGS_MODULE = settings.test` is silently ignored and tests run against real MySQL
instead, which also makes `--no-deps` (skip starting the `database` container) unsafe to combine
with the plain `docker compose run --rm web pytest` form.

Running a single test (inside the container, e.g. via `make shell`):

```bash
pytest django_trips/tests/test_services.py
pytest django_trips/tests/test_services.py::CreateTripBookingTestCase::test_adds_the_party_to_booked_seats
pytest django_trips/management/tests/test_generate_trips.py
```

Test settings use `settings.test` (`DJANGO_SETTINGS_MODULE=settings.test` per `pytest.ini`), which imports
`settings.common` but swaps `DATABASES` to an in-memory SQLite backend - combined with `--no-migrations`,
tests build schema directly from models against SQLite, so new migrations aren't required for tests to pick
up model changes (but still create them for real deployments, which run against MySQL).

Linting:

```bash
python run_lint.py     # pylint over django_trips/, fails if score < 6 (see THRESHOLD in run_lint.py)
```

pep8speaks enforces max line length 120 on PR diffs only (`.pep8speaks.yml`); `.pylintrc` ignores `tests.py`,
`urls.py`, and `migrations` entirely.

## Git workflow

`main` is the base branch for `django-trips`. Never commit or merge directly into `main` (or any shared
branch) — always create a separate feature/fix branch off the **latest** `main` (checkout main, pull
main, then branch off it), push that branch, and open a PR. If you are already on a separate branch whose
PR hasn't merged yet, keep committing there. Once a branch's PR has merged, that branch is done — for the
next piece of work, pull `main` again and cut a fresh branch off it rather than continuing to commit to
the merged branch. Carry forward any local commits that haven't landed anywhere yet with `git cherry-pick`
onto the new branch, not by merging/rebasing the old branch's full history onto the new base.

## Architecture

### Domain model shape

Everything hangs off `Trip` (`django_trips/models.py`). Key relationships:

- `Trip` → `Host` (organizer) → `HostType`, `HostRating`
- `Trip` → `Location` (via `departure`, `destination` FKs and `locations` M2M) — `Location` is self-referential
  (`parent`) to form a region hierarchy (e.g. a TOWN's parent is a PROVINCE); `Location.region` derives the display
  region from that parent chain, not from a flat field.
- `Location` is a swappable model (`swapper`, the generalized `AUTH_USER_MODEL` pattern - see README's "Custom
  Location model") - every FK to it (`Trip.departure`/`destination`/`locations`, `TripItinerary.location`,
  `TripReview.location`, `Testimonial.location`, `TripPickupLocation.location`) is declared via
  `swapper.get_model_name("django_trips", "Location")`, not the bare class, and `get_location_model()`
  (`models.py`) is how code reaches "whichever model is actually active" rather than importing `Location`
  directly. A consumer reads a location's fields through `django_trips.location_adapter.get_location_adapter()`
  instead of by field name, so an installer's own swapped-in model doesn't need matching field names - only a
  `DJANGO_TRIPS_LOCATION_ADAPTER` override. The REGION-rollup hierarchy behavior (`expand_destination_slugs`,
  `destinations_with_trip_counts` and `trips_booked_to` in `locations.py`) is `Location`'s
  own `parent`/`type` concept, not part of that adapter contract, and only works against the default, unswapped
  model. `get_active_locations_queryset()` (used everywhere a location choice is offered on create/update)
  checks for an `active()` method on the swapped-in model's manager and falls back to every row, active or
  not, if it's absent - not part of the adapter contract either, for the same reason (a swapped-in model
  isn't guaranteed to have an active/inactive concept at all). `AbstractLocation` (`models.py`) is a plain
  abstract Django model - the same shape `AbstractUser` is, real fields and concrete methods, not an
  interface class - an installer building a brand-new custom Location model can inherit directly instead of
  writing a `LocationAdapter` subclass; see README's "Custom Location model" for when to reach for which.
- `Trip` → `Category`, `Facility`, `Gear` (M2M lookup-style models, all sharing `ActiveQuerySet`/`is_active`
  filtering via `managers.py`)
- `Trip` → `TripAvailability` (a recurrence rule: DAILY/WEEKLY/MONTHLY/FIX_DATE + a price/seat window) →
  `Trip.create_schedules()` expands a DAILY availability into concrete `TripSchedule` rows (one per bookable date,
  capped at 20 days per call). See the docstring on `create_schedules` for the full expansion flow.
- `TripSchedule` (dated, priced, bookable instance of a trip) → `TripBooking` (a customer's booking against one
  schedule, with an auto-generated `DPT######NN`-style reference number and a `BookingStatus` state machine —
  the allowed transitions are documented in `choices.py` on `BookingStatus`, and `can_be_cancelled`/`is_cancelled`
  are the canonical checks, not ad-hoc string comparisons).
- `Trip.starting_price` is computed as the min `base_price` across a trip's packages, not stored — packages
  aren't date-bound, so no active/upcoming schedule filtering applies (unlike the older schedule-based model).
  `TripSchedule.additional_price`/`additional_child_price` is a flat per-date surcharge added on top of whichever
  package is booked, resolved via `get_effective_price()` (`services.py`) — see `README.md`'s "Pricing model"
  section for the full package/schedule pricing shape.
- `TripReview` (an individual, per-trip rating breakdown) is distinct from `TripReviewSummary` (a curated,
  one-to-one *rollup* per trip — not auto-computed from `TripReview` rows) which is in turn distinct from
  `Testimonial` (freeform, site-wide marketing quotes not tied to a specific trip) — don't conflate these when
  adding review-related features. The public review count is `TripReview.objects.verified()`, not every row.
- `CancellationPolicy`/`RefundPolicy` are `ConfigurationModel` (django-config-models) singletons for the
  host-wide default; `Trip.cancellation_policy`/`refund_policy` properties prefer the host's own policy over these
  defaults when set.
- `TripWishlist` is a simple `(user, trip)` join (unique together) for a user's saved/wishlisted trips, toggled via
  `services.toggle_trip_wishlist()`.

### Business rules

Rules live in `services.py` (writes) and the model querysets in `managers.py` (reads), so every consumer's API,
management command or admin action gets the same behavior:

- `create_trip_booking()` owns booking: terms, the selection belonging to the trip (`validate_trip_booking()`,
  zero queries), the seat check under `select_for_update()` on the schedule, pricing via `get_effective_price()`,
  the Standard package fallback, and the `booked_seats` update. `create_trip()`/`update_trip()` own trip writes
  (categories are additive-only on update; the itinerary is upserted by `day_index`).
- A rule failure raises Django's `ValidationError` with a dict keyed by field, for the consumer's API to turn
  into its own error response.
- Read-side: `Trip.objects.with_price()` / `TripSchedule.objects.with_price()` (the annotation is named
  `price` so a consumer's `?ordering=price` can sort on it, and can't be `starting_price`, a setter-less model property), and
  `with_trip_counts()` on categories, trust badges and hosts, `TripSchedule.objects.bookable()` (upcoming +
  published), `TripReview.objects.verified()`, and `TripBooking.objects.matching_guest()` (the guest lookup, never
  on `number` alone). `services.toggle_trip_wishlist()` owns the wishlist toggle. Location queries
  (`expand_destination_slugs`, `destinations_with_trip_counts`, `trips_booked_to`) are functions in
  `locations.py`, not manager methods, because `Location` is swappable.
- Tests run on SQLite, which ignores `select_for_update()`, so the lock is tested by asserting it is requested.

### Management commands

`generate_trips` (`django_trips/management/commands/generate_trips.py`) seeds fake trips/hosts/locations for local
dev, driven by the `TRIP_*` settings in `settings/common.py` (`TRIP_DESTINATIONS`, `TRIP_HOSTS`,
`TRIP_LOCATIONS_BY_REGION`, etc.) unless the consuming project sets `USE_DEFAULT_TRIPS=True`. When adding new
seed-relevant settings, update both `settings/common.py` and the README's "Generate random trips" section together.

### Settings

`settings/common.py` is the real settings module (Docker sets `DJANGO_SETTINGS_MODULE=settings.common`);
`settings/test.py` re-exports it for pytest but swaps `DATABASES` to an in-memory SQLite backend (see
"Common commands" above for how `make test` forces this to actually take effect). `devsite/wsgi.py`/
`asgi.py`/`urls.py` are the minimal dev-only project shell and aren't part of the published package.

`DATABASES` reads `DATABASE_ENGINE`, defaulting to `django.db.backends.sqlite3` if unset - matching the
pattern well-known reusable Django apps (django-oscar, wagtail) use. `make dev.up` (`docker compose up`,
no profile) now runs against SQLite by default, with no `database` container involved at all - that
service carries `profiles: [mysql]` in `docker-compose.yml`, so it only starts when explicitly asked
for (`docker compose --profile mysql up`), and `web` itself only connects to it once `DATABASE_ENGINE=
django.db.backends.mysql` is set in `.env` too - the profile alone isn't enough, both are required
together, on purpose. `mysqlclient` is installed via its own `RUN pip install` line in the `Dockerfile`
rather than listed as a project dependency, so it stays outside GitHub's dependency graph/Dependabot
scanning entirely - it's dev-only either way, and only ever used when the MySQL opt-in above is active.
`web` no longer has a `depends_on: database` health-gate (it would break the profile-less default
case, since Compose can't depend on a profile-gated service that isn't active) - so on a fresh MySQL
opt-in, `web`'s first `migrate` can race `database`'s startup and fail once; `restart: unless-stopped`
retries it automatically and it recovers within a few seconds once MySQL is healthy. Not a bug, just
the trade-off of making MySQL truly optional.

## Testing conventions

Tests are `django.test.TestCase` subclasses, not bare `@pytest.mark.django_db`-decorated functions -
`django_hotels`/`django_rentals` and destipak's own per-vertical apps (`djangoapps/trip_hosts/`,
`djangoapps/hotel_owners/`, `djangoapps/rental_operators/`) follow the same convention. Build fixtures
via `django_trips/tests/factories.py` (`HostFactory`, `TripFactory`, etc.) rather than calling
`Model.objects.create(...)` directly in a test - `django_hotels/tests/factories.py` and
`django_rentals/tests/factories.py` mirror this module's shape one vertical over each. A raw
`.objects.create()` is still fine for a test whose whole point is model/manager mechanics.

## Packaging

**This package is published to PyPI - every change here ships to real installs, not just
this repo's own Docker dev setup.** The known consumer today is destipak (via an editable
VCS install - see its own `requirements/base.in`), but this package has 24+ real PyPI
releases going back years, well before destipak existed - there may be other installs in
the wild with no visibility into this repo at all. Treat every change as a public release,
not a local edit. Before changing anything packaging-related (`pyproject.toml`, module
layout, `__init__.py`, entry points, dependency ranges) or any public import path/behavior,
check it against real installer protocols: does `pip install django-trips` still work, does
an editable VCS install (`pip install -e git+https://...#egg=django-trips`) still resolve,
does `python -m build` + `twine check` still pass. Verify with an actual install and a real
build, not just the local test suite - a change that only works when edited in place inside
this repo isn't finished.

All metadata lives in `pyproject.toml` alone (no `setup.py`/`setup.cfg`/`MANIFEST.in`) -
PEP 621 `[project]` table plus `[tool.setuptools]` for the `src/` layout and package
discovery. Same shape as `django_hotels`/`django_rentals`; three things worth knowing:

- **Version is derived from the git tag, not hand-maintained.** `src/django_trips/__init__.py`
  reads `__version__` via `importlib.metadata.version("django-trips")` at import time -
  `setuptools-scm` (`[tool.setuptools_scm]`) computes that version from `git describe` at
  build time, so tagging *is* the version bump. `.github/workflows/release.yaml` cross-checks
  this: it runs `python -m setuptools_scm` after checkout and fails the release if it doesn't
  exactly match the pushed tag. Local Docker dev has no git tag history to derive from, so the
  `Dockerfile` sets `SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0.dev0` as the documented escape hatch.
- **This repo's git tags mix two eras** - a legacy `v`-prefixed series (`v0.2.1` through
  `v2.8`, all pointing at commits from 2021 or earlier) and the current bare-number scheme
  (`1.0.2` onward, matching what's actually live on PyPI). `setuptools-scm`'s default tag
  matching resolved correctly against the bare-number series when checked (`git describe`
  walks commit ancestry, not version-number ordering, and the `v`-prefixed tags are all on
  old commits), but always tag new releases without the `v` prefix - don't resurrect it.
- **`include-package-data` is explicitly turned off** (`[tool.setuptools]`). PEP 621 metadata
  defaults it to `true`, which - combined with setuptools-scm's git-file-finder - sweeps every
  git-tracked file under a found package's directory into the wheel as "package data",
  bypassing `packages.find`'s `exclude` entirely. This package ships no non-Python data files,
  so turning it off is the correct fix - don't re-enable it without re-checking wheel contents
  (`python -m zipfile -l dist/*.whl`) afterward.

`django_trips.tests` (the factories module referenced in "Testing conventions" above) ships in
the built package deliberately; `django_trips.management.tests` (this package's own internal test
suite, not documented as consumer-facing anywhere) is excluded via `packages.find`'s `exclude`.

Releasing is CI-only: pushing a version tag triggers `release.yaml`, which builds, runs
`twine check`, and publishes via PyPI Trusted Publishing (OIDC - `permissions: id-token:
write`, no stored token). There's deliberately no local/manual publish path in the
`Makefile` - one existed before (`make publish.test`/`publish.prod`) but it both duplicated
this pipeline with a legacy `setup.py sdist bdist_wheel` invocation and bypassed its
version-gate and OIDC auth, so it was removed rather than updated for the new layout.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`django-trips` is a reusable Django app (published as a pip package, see `setup.cfg`) providing a REST API for
managing trips, schedules, bookings, hosts, and locations. It's the core trips service behind the
[DestinationPak](https://destinationpak.com) platform. Consumers install it and mount its URLs under a namespace of
their choosing (see README "Usage").

Note the two similarly-named top-level packages: `django-trips/` (hyphen) is the throwaway Django *project* shell
used only for local dev (`settings.py`-style `urls.py`, `wsgi.py`, `asgi.py`); `django_trips/` (underscore) is the
actual app that gets published and contains all real logic.

## Common commands

All development happens inside Docker; there is no supported bare-metal workflow.

```bash
make build          # docker compose build (destroys existing containers first)
make dev.up          # start web (SQLite by default - see "Settings" below for the MySQL opt-in)
make shell           # attach a shell inside the web container (django-shell alias)
make update_db        # run migrations
make random_trips      # seed random trips (generate_trips --batch_size=100)
make test            # docker compose run --rm web pytest
make stop / make destroy  # stop / tear down containers (destroy removes volumes too)
make logs            # tail web container logs
```

Running a single test (inside the container, e.g. via `make shell`):

```bash
pytest django_trips/api/tests/test_trip_list.py
pytest django_trips/api/tests/test_trip_list.py::SomeTestCase::test_something
pytest django_trips/management/tests/test_generate_trips.py
```

Test settings use `settings.test` (`DJANGO_SETTINGS_MODULE=settings.test` per `pytest.ini`), which just imports
`settings.common` with `--no-migrations` — tests build schema directly from models, so new migrations aren't
required for tests to pick up model changes (but still create them for real deployments).

Linting:

```bash
python run_lint.py     # pylint over django_trips/, fails if score < 6 (see THRESHOLD in run_lint.py)
```

pep8speaks enforces max line length 120 on PR diffs only (`.pep8speaks.yml`); `.pylintrc` ignores `tests.py`,
`urls.py`, and `migrations` entirely.

## Git workflow

`master` is the base branch for `django-trips`. Never commit or merge directly into `master` (or any shared
branch) — always create a separate feature/fix branch off the **latest** `master` (checkout master, pull
master, then branch off it), push that branch, and open a PR. If you are already on a separate branch whose
PR hasn't merged yet, keep committing there. Once a branch's PR has merged, that branch is done — for the
next piece of work, pull `master` again and cut a fresh branch off it rather than continuing to commit to
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
  directly. Every place this app reads a location's fields for API output goes through
  `django_trips.location_adapter.get_location_adapter()` (`LocationSerializer`, `DestinationWithSchedulesSerializer`,
  `TripReviewSerializer`/`TestimonialSerializer`'s `get_location`) instead of reading field names off the model, so
  an installer's own swapped-in model doesn't need matching field names - only a `DJANGO_TRIPS_LOCATION_ADAPTER`
  override. The REGION-rollup hierarchy behavior (`expand_destination_slugs` in `api/filters.py`,
  `ActiveDestinationsWithSchedulesView`'s queryset, `DestinationWithSchedulesSerializer.get_schedules`) is `Location`'s
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
  adding review-related features. `get_trip_review_summary_data()` in `api/serializers.py` is the shared helper
  (used by both `TripListSerializer` and `TripDetailSerializer`) that renders `TripReviewSummary` as all-zero
  defaults when none has been curated yet, plus a `reviews_count` of verified `TripReview` rows — it's a plain
  function rather than a serializer-mixin field because DRF's `ModelSerializer` silently auto-builds a field from
  the model when a same-named field is declared on a non-`Serializer` base class.
- `CancellationPolicy`/`RefundPolicy` are `ConfigurationModel` (django-config-models) singletons for the
  host-wide default; `Trip.cancellation_policy`/`refund_policy` properties prefer the host's own policy over these
  defaults when set.
- `TripWishlist` is a simple `(user, trip)` join (unique together) for a user's saved/wishlisted trips, toggled via
  `TripViewSet.wishlist` (`POST /trips/<identifier>/wishlist/`). The `is_wished` field on
  `TripListSerializer`/`TripDetailSerializer` is backed by a `wished_trip_ids` set precomputed once per request in
  `TripViewSet.get_serializer_context` (avoids an `exists()` query per trip on `/trips/`); `get_is_wished()` in
  `api/serializers.py` falls back to a direct per-object query when that context key is absent, e.g. when
  `TripDetailSerializer` is rendered nested inside `TripBookingSerializer`.

### API layer

- `django_trips/api/urls.py` wires a DRF `DefaultRouter` (`TripViewSet`, booking viewset) plus explicit `path()`
  entries for endpoints that don't fit REST-router conventions (upcoming trips, destinations, categories, nested
  booking creation). drf-spectacular serves schema/swagger/redoc from the same urlpatterns.
- `TripViewSet.lookup_field = "identifier"` — trip detail/update/delete accept either a numeric PK or a slug
  (`get_object()` branches on `identifier.isdigit()`). Any new single-trip endpoint should follow this convention.
- Serializer/permission selection is action-based (`get_serializer_class`, permission via
  `IsAuthenticatedOrReadOnly` + `IsStaffForDeleteOnly`): list/retrieve are public, create/update need auth, delete
  needs staff. PATCH is deliberately unsupported (`http_method_names` excludes it).
- Filtering uses `django_filters`, not ad-hoc query param parsing. `TripFilter`/`UpcomingTripsFilter` in
  `api/filters.py` are the pattern to extend. Note `TripFilter.filter_queryset`: price/date filters are
  intentionally *not* independent per-field django-filter fields — they're combined into a single `Q` against
  `TripSchedule` in `filter_queryset()` so a trip only matches if *one* schedule satisfies all constraints together
  (otherwise a trip could match via two different schedules, e.g. a cheap-but-past one and an
  expensive-but-future one). Follow this combined-constraint pattern for any new multi-field schedule filter.
- Ordering uses DRF's `OrderingFilter`, and where ordering is by an annotated/computed value (e.g. `?ordering=price`
  on `TripViewSet.list`), the queryset annotation name must exactly match the ordering field name — DRF orders by
  the literal client-supplied term, not an alias — and must not collide with an existing model property name (see
  the comment above `TripViewSet.ordering_fields`, and `get_queryset()`'s `Min("schedules__price", ...)`
  annotation, both scoped to `status=ScheduleStatus.PUBLISHED`).
- `api/paginators.py` has three styles, none of which is set explicitly on the *most* views: `CustomLimitOffsetPaginator`
  (limit/offset, used by `TripViewSet`/`UpcomingTripsListAPIView`) and `TripBookingsPagination` (page-number style,
  default DRF envelope, used by the booking list/create views in `api/views/booking.py`) are both explicitly set as
  `pagination_class` on their views. `TripResponsePagination` (a page-number paginator with a custom
  `{next, previous, count, current, pages, results}` envelope) is `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` in
  `settings/common.py` — no view sets it explicitly, but it's still live as the fallback on any view that doesn't
  override `pagination_class` (currently `ActiveCategoriesListAPIView` and `ActiveDestinationsWithSchedulesView`).
  Match whichever style the endpoint you're touching already uses; they are not interchangeable response shapes for
  existing clients.
- Auth is dual: `SessionAuthentication` (browsable API) and JWT (`rest_framework_simplejwt`, 7-day access /
  15-day refresh, see `SIMPLE_JWT` in `settings/common.py`).

### Management commands

`generate_trips` (`django_trips/management/commands/generate_trips.py`) seeds fake trips/hosts/locations for local
dev, driven by the `TRIP_*` settings in `settings/common.py` (`TRIP_DESTINATIONS`, `TRIP_HOSTS`,
`TRIP_LOCATIONS_BY_REGION`, etc.) unless the consuming project sets `USE_DEFAULT_TRIPS=True`. When adding new
seed-relevant settings, update both `settings/common.py` and the README's "Generate random trips" section together.

### Settings

`settings/common.py` is the real settings module (Docker sets `DJANGO_SETTINGS_MODULE=settings.common`);
`settings/test.py` just re-exports it for pytest. `django-trips/wsgi.py`/`asgi.py`/`urls.py` are the minimal dev-only
project shell and aren't part of the published package.

`DATABASES` reads `DATABASE_ENGINE`, defaulting to `django.db.backends.sqlite3` if unset - matching the
pattern well-known reusable Django apps (django-oscar, wagtail) use. `make dev.up` (`docker compose up`,
no profile) now runs against SQLite by default, with no `database` container involved at all - that
service carries `profiles: [mysql]` in `docker-compose.yml`, so it only starts when explicitly asked
for (`docker compose --profile mysql up`), and `web` itself only connects to it once `DATABASE_ENGINE=
django.db.backends.mysql` is set in `.env` too - the profile alone isn't enough, both are required
together, on purpose. `mysqlclient` is installed via its own `RUN pip install` line in the `Dockerfile`
rather than listed in `requirements.txt`, so it stays outside GitHub's dependency graph/Dependabot
scanning entirely - it's dev-only either way, and only ever used when the MySQL opt-in above is active.

## Testing conventions

Tests are `django.test.TestCase` subclasses, not bare `@pytest.mark.django_db`-decorated functions -
`django_hotels`/`django_rentals` and destipak's own per-vertical apps (`djangoapps/trip_hosts/`,
`djangoapps/hotel_owners/`, `djangoapps/rental_operators/`) follow the same convention. Build fixtures
via `django_trips/tests/factories.py` (`HostFactory`, `TripFactory`, etc.) rather than calling
`Model.objects.create(...)` directly in a test - `django_hotels/tests/factories.py` and
`django_rentals/tests/factories.py` mirror this module's shape one vertical over each. A raw
`.objects.create()` is still fine for a test whose whole point is model/manager mechanics.

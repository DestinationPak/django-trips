# Architecture

django-trips ships models, querysets, business rules (`services.py`) and admin. It has no API, views or URLs (the DRF API was removed in 2.0.0): each project builds its own endpoints on the services and querysets.

## Domain model

Everything hangs off `Trip` (`django_trips/models.py`).

- `Trip` → `Host` (organizer) → `HostType`, `HostRating`.
- `Trip` → `Category`, `Facility`, `Gear`: M2M lookup models sharing `ActiveQuerySet`/`is_active` filtering (`managers.py`).
- `Trip` → `TripAvailability`, a recurrence rule (DAILY/WEEKLY/MONTHLY/FIX_DATE plus a price/seat window). `Trip.create_schedules()` expands a DAILY availability into concrete `TripSchedule` rows, one per bookable date, capped at 20 days per call; its docstring has the full flow.
- `TripSchedule` (a dated, priced, bookable instance) → `TripBooking` (one customer's booking, with a `DPT######NN`-style reference number). `BookingStatus` in `choices.py` documents the allowed transitions; use `can_be_cancelled`/`is_cancelled`, never string comparisons.
- `Trip.starting_price` is computed as the minimum `base_price` across the trip's packages, not stored. Packages aren't date-bound. `TripSchedule.additional_price`/`additional_child_price` is a flat per-date surcharge on top of the booked package, resolved by `get_effective_price()` (`services.py`). See the README's "Pricing model".
- Three separate review concepts, don't conflate them:
  - `TripReview`: an individual per-trip rating breakdown. The public count is `TripReview.objects.verified()`, not every row.
  - `TripReviewSummary`: a curated one-to-one rollup per trip, not computed from `TripReview`.
  - `Testimonial`: freeform site-wide marketing quotes, not tied to a trip.
- `CancellationPolicy`/`RefundPolicy` are `ConfigurationModel` (django-config-models) singletons for the default; `Trip.cancellation_policy`/`refund_policy` prefer the host's own policy when set.
- `TripWishlist` is a `(user, trip)` join (unique together), toggled by `services.toggle_trip_wishlist()`.

## Location is swappable

`Location` is self-referential (`parent`) to form a region hierarchy (a TOWN's parent is a PROVINCE); `Location.region` derives the display region from the parent chain.

It is also a swappable model (`swapper`, the generalized `AUTH_USER_MODEL` pattern; see the README's "Custom Location model"):

- Every FK to it (`Trip.departure`/`destination`/`locations`, `TripItinerary.location`, `TripReview.location`, `Testimonial.location`, `TripPickupLocation.location`) is declared with `swapper.get_model_name("django_trips", "Location")`, never the bare class.
- Code reaches the active model through `get_location_model()` (`models.py`), never by importing `Location`.
- Consumers read a location's fields through `django_trips.location_adapter.get_location_adapter()`, so a swapped-in model only needs a `DJANGO_TRIPS_LOCATION_ADAPTER` override, not matching field names.
- `AbstractLocation` (`models.py`) is a plain abstract model (like `AbstractUser`) that an installer can inherit instead of writing a `LocationAdapter` subclass.

Not part of the adapter contract:

- The REGION rollup (`expand_destination_slugs`, `destinations_with_trip_counts`, `trips_booked_to` in `locations.py`) relies on `Location`'s own `parent`/`type`, and only works where the model has them. These are functions in `locations.py`, not manager methods, because the model is swappable.
- `get_active_locations_queryset()` (used wherever a location is chosen on create/update) calls the manager's `active()` if it exists and silently falls back to every row if not.

## Business rules

Writes live in `services.py` and reads in the querysets in `managers.py`, so every consumer's API, command or admin action behaves the same.

- `create_trip_booking()` owns booking: terms, the selection belonging to the trip (`validate_trip_booking()`, zero queries), the seat check under `select_for_update()` on a `bookable()` schedule, pricing via `get_effective_price()`, the Standard package fallback, and the `booked_seats` update.
- `cancel_trip_booking()` (which refuses a booking that can't be cancelled unless `check_cancellable=False`) and `delete_trip_booking()` give seats back. The release is floored at zero (`Greatest(F("booked_seats"), party) - party`) because `booked_seats` is unsigned on MySQL.
- `create_trip()`/`update_trip()` own trip writes: categories are additive-only on update; the itinerary is upserted by `day_index`.
- A rule failure raises Django's `ValidationError` with a dict keyed by field, for the consumer's API to turn into its own error response.
- The admin goes through the same services: setting a booking to cancelled calls the cancel service, deletes call the delete service, and a cancelled booking can't be reopened.

Read side:

- `Trip.objects.with_price()` / `TripSchedule.objects.with_price()`: the annotation is named `price` so `?ordering=price` can sort on it (it can't be `starting_price`, a setter-less property).
- `with_trip_counts()` on categories, trust badges and hosts.
- `TripSchedule.objects.bookable()`: upcoming and published.
- `TripReview.objects.verified()`.
- `TripBooking.objects.matching_guest()`: the guest lookup, never on `number` alone.

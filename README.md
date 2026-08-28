# Django Trips API

This is a Django REST API for managing and retrieving trips, schedules, bookings, and related travel data.

This service is a core component of the [DestinationPak](https://destinationpak.com) project — a platform designed 
to make exploring and booking adventures across Pakistan easier and more accessible.

## Installation
Simply do:
```bash
pip install django-trips
```

## Usage
Add the app into your installed apps in your project's settings file. 
```
INSTALLED_APPS = [
    ...
    'django_trips',
]
```
## Migrate
```
python manage.py migrate 
```
Add the following to your root `urls.py` or to your desired file location.   
```
urlpatterns = [
    ...
    path('trips/', include('django_trips.urls')),
]
```
This mounts the whole app under your own chosen namespace (`trips/` above - replace with
whatever prefix you like) with the lib's own `v1/` version underneath it, e.g.
`trips/v1/trips/`, `trips/v1/schema/redoc/`. The app versions itself independently of
your project's own API version, so bumping *your* API to `v2` doesn't imply anything
changed in this lib, and vice versa.

If you'd rather skip the lib's own version segment and wire the endpoints directly into
your own scheme, include `django_trips.api.urls` instead:
```
urlpatterns = [
    ...
    path('trips/', include(('django_trips.api.urls', 'trips-api'), namespace='trips-api')),
]
```

`Trip.get_absolute_url()` and `TripListSerializer`/`TripDetailSerializer`'s `trip_url`
field both need to resolve `trip-detail`'s URL. The serializers do this off the current
request's own resolved namespace, so they work regardless of where you've mounted these
views. `get_absolute_url()` has no request to read that from (e.g. Django admin's "View
on site" calls it bare), so it defaults to the `trips-api` namespace shown above; if you
mount these views under a different namespace instead - e.g. re-exposing them under your
own project's URL scheme rather than including this app's urls.py directly - set
`DJANGO_TRIPS_URL_NAMESPACE` in your settings to match.

## Custom Location model

`django_trips.Location` (a self-hierarchical `name`/`slug`/`lat`/`lon`/`type`/`parent` model,
used by `Trip.departure`/`Trip.destination`/`Trip.locations`, `TripItinerary.location`,
`TripReview.location`, `Testimonial.location`, and `TripPickupLocation.location`) is
swappable, the same way Django's own `AUTH_USER_MODEL` is - if your project already has its
own location/city model, you don't have to duplicate location data into a second table just
to install this app.

Two settings, both optional and both defaulting to this package's own bundled model:

- **`DJANGO_TRIPS_LOCATION_MODEL`** - an `"app_label.ModelName"` string naming which model
  actually satisfies the FK, e.g. `DJANGO_TRIPS_LOCATION_MODEL = "myapp.City"`. Your model
  doesn't need to share `Location`'s field names.
- **`DJANGO_TRIPS_LOCATION_ADAPTER`** - a dotted path to a `django_trips.location_adapter
  .LocationAdapter` subclass telling this app how to read your model's fields as if they were
  `Location`'s (`get_name`, `get_slug`, `get_lat`, `get_lon`, `get_type_display`, `get_region`,
  `get_travel_tips`, `get_importance`, `get_poster`). Every place this app reads a location for
  API output goes through `django_trips.location_adapter.get_location_adapter()`, never by
  field name directly, so your adapter is the only place that needs to know your model's real
  shape.

**Set both before your project's first `migrate`.** Like `AUTH_USER_MODEL`, this is a
swappable-model setting - Django resolves it once when the app loads, and a swap made after
`Location`'s own table has already been created (and other tables have already foreign-keyed
into it) doesn't retroactively move that data; it needs a real data migration instead of a
config change.

Building a brand-new Location model rather than reusing one you already have? Inherit
`django_trips.models.AbstractLocation` instead of writing an adapter - it's a plain abstract
Django model (the same shape `AbstractUser` is - real fields and concrete methods, not an
interface class) already carrying `name`/`slug`/`lat`/`lon`/`type`/`parent`/`region`/
`travel_tips`/`importance`/`poster_image`/`poster_url` and their read methods, so you get a
working swap with no `DJANGO_TRIPS_LOCATION_ADAPTER` at all:

```python
# myapp/models.py
from django_trips.models import AbstractLocation

class MyLocation(AbstractLocation):
    country_code = models.CharField(max_length=2, default="PK")
```

```python
# settings.py
DJANGO_TRIPS_LOCATION_MODEL = "myapp.MyLocation"
```

Reusing an existing model instead - one you can't restructure, or one shared with other
libraries - stick with the adapter approach above; that's what it's for.

A few features are tied to `Location`'s own hierarchy shape (`type`/`parent`) rather than the
adapter's field-level contract - the REGION-rollup search behavior (`expand_destination_slugs`
in `api/filters.py`) and `ActiveDestinationsWithSchedulesView`/`DestinationWithSchedulesSerializer`'s
region grouping. These assume the default, unswapped `Location` model and aren't guaranteed to
work against an arbitrary swapped-in model that doesn't share that hierarchy concept.

For a worked example of a real swap: the DestinationPakistan platform (this package's own
primary consumer, a private project) points this setting at its own `public.City` model via a
`TripsCityLocationAdapter` in its `djangoapps/public/adapters.py` - the same shape sketched
above, just concretely filled in.

## Trip status events

Every time a `Trip`'s `status` actually changes value on save (editing an existing trip,
not creating one), the lib records a `TripStatusEvent` row and fires a `trip_status_changed`
signal (`django_trips/signals.py`) carrying `trip`, `old_status`, `new_status`, `changed_by`,
and `reason`. Use `Trip.set_status(new_status, changed_by=user, reason="payment confirmed")`
to attribute a change to a specific staff user and/or a reason; a bare
`trip.status = ...; trip.save()` still logs an event, just with `changed_by=None` (read as
system/automatic) and an empty `reason`.

`trip_status_changed` is a plain Django signal, so a consuming project can change this
behaviour without forking the lib:
```python
from django_trips.signals import log_trip_status_event, trip_status_changed
from django_trips.models import Trip

# Replace the default DB logging entirely:
trip_status_changed.disconnect(log_trip_status_event, sender=Trip)

# Or just react to it in addition to the default logging, e.g. a notification:
trip_status_changed.connect(notify_status_change, sender=Trip)
```

## Booking status events

`TripBooking` has the same arrangement: a status change on an existing booking records a
`BookingStatusEvent` and fires `booking_status_changed` (kwargs `booking`, `old_status`,
`new_status`, `changed_by`, `reason`), with `TripBooking.set_status()` and the same
disconnect/connect override mechanism as above. `TripBooking.cancel(changed_by=..., reason=...)`
goes through `set_status`, so cancellations land in the same history.

The events are what backs a traveler-facing "booking activity" timeline —
`TripBookingSerializer` exposes them as a read-only `status_events` list (including on the
anonymous lookup endpoint), deliberately without `changed_by`: which staff member actioned a
booking isn't the traveler's business. Note that no event is logged at creation, so a
booking that has never moved off `PENDING` has an empty list; render the booking's own
`created` timestamp for that first "booking placed" entry.

## Pricing model

Price lives in two places, and they compose rather than compete:

- **`TripPackage.base_price` / `base_child_price`** — the source-of-truth adult/child
  price for a pricing tier (Standard/Budget/Premium/...). This is an absolute,
  date-independent menu price, set once per tier rather than on every schedule.
- **`TripSchedule.additional_price` / `additional_child_price`** — a flat *surcharge*
  for one specific bookable departure date (e.g. weekend/holiday/peak pricing), added
  on top of whichever package the traveler is booking against. 0 for a regular date.

The final payable price for a package + (optional) schedule + (optional) pickup
location is always resolved via `get_effective_price()`
(`django_trips/services.py`), never by reading `TripPackage`'s fields directly:

```python
from django_trips.services import get_effective_price

get_effective_price(package, schedule=schedule, pickup=pickup)
# {"price": package.base_price + schedule.additional_price + pickup.additional_price,
#  "child_price": package.base_child_price + schedule.additional_child_price + pickup.additional_price}
```

Every `Trip` is guaranteed to always have exactly one **"Standard"** package,
auto-created by a `post_save` signal the moment the trip is saved
(`django_trips/signals.py`) at `base_price=0`/`base_child_price=0` until an admin
sets a real price. Booking a trip that offers no extra tiers still resolves to a
real package under the hood — **no manual package-creation step is required for a
simple, single-price trip.**

### Worked example — a plain 2-night domestic trip, no tiers, no date surcharge

Say a 2-night trip to Hunza has its Standard package priced at `base_price=15000`,
`base_child_price=8000`, with no extra tiers beyond the automatic Standard one,
and no schedule surcharge:

```python
trip = Trip.objects.create(name="2 Nights in Hunza", ...)   # Standard package auto-created here

standard_package = trip.packages.get(name=PackageTier.STANDARD)
standard_package.base_price = 15000
standard_package.base_child_price = 8000
standard_package.save()

schedule = TripSchedule.objects.create(trip=trip, ...)   # additional_price=0 by default

get_effective_price(standard_package, schedule=schedule)
# {"price": 15000, "child_price": 8000}
```

A booking for 2 adults and 1 child on this schedule (via
`POST /trips/<trip_id>/bookings/create/`, omitting `package` so it defaults to
Standard) stores `total_price = 15000 * 2 + 8000 * 1 = 38000` — no package tier
had to be created or selected for this to work correctly.

## Generate random trips.
Before you generate random scripts, make sure you have the required settings available in your project. If you want to use the default settings set `USE_DEFAULT_TRIPS=True`. 
The script depends upon these variables, if you don't want to use the default settings set the 
following settings. 
1. `TRIP_DESTINATIONS`
2. `TRIP_DEPARTURE_LOCATION`
3. `TRIP_LOCATIONS = TRIP_DEPARTURE_LOCATION + TRIP_DESTINATIONS`
4. `TRIP_LOCATIONS_BY_REGION` (optional) - maps each location name above to its
   PROVINCE-level parent, e.g. `{"Gilgit-Baltistan": ("Hunza", "Skardu")}`, so
   `Location.region` resolves instead of staying `None`.
5. `TRIP_HOSTS`
6. `TRIP_FACILITIES`
7. `TRIP_CATEGORIES`
8. `TRIP_GEARS`

```
python manage.py generate_trips --batch_size=100
``` 
Change the `batch_size` variable to create as much of trips you want. 

## Developer Docs & API Documentation
You can access the all available API endpoints on the following links.
* http://localhost:8000/api/v1/schema/redoc
* http://localhost:8000/api/v1/schema/swagger-ui/

## API Endpoints
The following pages are served in the development:

| Page                    | Method | URL                                                          |
|-------------------------|--------|--------------------------------------------------------------|
| All Trips List          | GET    | http://localhost:8000/api/v1/trips/                          |
| Upcoming Trips List     | GET    | http://localhost:8000/api/v1/trips/upcoming/                 |
| Search Trip             | GET    | http://localhost:8000/api/v1/trips/upcoming/?name=Boston      |
| Single Trip             | GET    | http://localhost:8000/api/v1/trips/{identifier}/             |
| Update Trip             | PUT    | http://localhost:8000/api/v1/trips/{identifier}/             |
| Delete Trip             | DELETE | http://localhost:8000/api/v1/trips/{identifier}/             |
| Create Trip             | POST   | http://localhost:8000/api/v1/trips/                          |
| Toggle Trip Wishlist    | POST   | http://localhost:8000/api/v1/trips/{identifier}/wishlist/     |
| Destinations List       | GET    | http://localhost:8000/api/v1/destinations/                   |
| Destinations Detail     | GET    | _TODO_                                                         |
| All Trip Bookings       | GET    | http://localhost:8000/api/v1/trips/{trip_id}/bookings/       |
| Book a Trip             | POST   | http://localhost:8000/api/v1/trips/{trip_id}/bookings/create/ |
| Booking Details         | GET    | http://localhost:8000/api/v1/trips/bookings/{number}/        |
| Update Booking          | PUT    | http://localhost:8000/api/v1/trips/bookings/{number}/        |
| Cancel Booking          | POST   | http://localhost:8000/api/v1/trips/bookings/{number}/cancel/ |
| Review Trip             | GET    | _TODO_                                                         |
| Trip Reviews & Comments | GET    | _TODO_                                                         |

### Filtering & ordering

`GET /trips/` supports the following query parameters (see `TripFilter` in `api/filters.py`):

| Param                          | Description                                                    |
|---------------------------------|------------------------------------------------------------------|
| `name`                          | Case-insensitive partial match on trip name                     |
| `destination`                    | Comma-separated destination slugs, e.g. `?destination=hunza,skardu` |
| `category`                       | Comma-separated category slugs, e.g. `?category=hiking,camping` |
| `duration_from` / `duration_to`  | Trip duration in days (inclusive)                                |
| `price_from` / `price_to`        | Only matches trips with a single published schedule in this price range |
| `date_from` / `date_to`          | Only matches trips with a single published schedule in this date range (`YYYY-MM-DD`) |
| `ordering`                       | One of `name`, `duration`, `price`; prefix with `-` for descending, e.g. `?ordering=-price` |

`GET /trips/upcoming/` supports its own equivalent set of filters (`name`, `price_from`/`price_to`,
`date_from`/`date_to`, `destination`, `duration_from`/`duration_to`) plus
`?ordering=` on `trip__name`, `price`, `start_date`, or `trip__duration`.

### API permissions
| Authentication          | Token Life |   
|-------------------------|------------|
| `SessionAuthentication` | UNLIMITED  |
| `JWTAuthentication`     | 7 Days     |


| Permissions       |
|-------------------|
| `IsAuthenticated` |
| `IsAdminUser`     |


## Develop Django Trips
Kick the docker build using the following command. 
```
make build
``` 
This task may take few minutes. 

 
Once the build has been completed, spin up the docker and migrate the database. 
```bash
> make dev.up
> make shell 
> make update_db
```
Create a superuser with username `admin`.

``` bash
> make shell
> python manage.py createsuperuser
```

Create batch of trips. Run the following command inside docker shell.
```bash
> python manage.py  generate_trips --batch_size=100
OR
> make random_trips
```

## Test
Run tests using the following command.
```
make test
```
## Docker Commands

| Action                            | Command        |
|-----------------------------------|----------------|
| Run Server                        | `make dev.up`  |
| Trail Logs                        | `make logs`    |
| Attach sever                      | `make attach`  |
| Stop server                       | `make stop`    |
| * Destroy docker container.       | `make destroy` |

_* caution, this will remove all your data._

## How to Contribute

Contributions are welcome! Whether it's bug fixes, new features, 
improving documentation, or sharing feedback — we'd love your help.

Please fork the repository, make your changes in a feature branch, 
and submit a pull request. For major changes, consider opening an issue
first to discuss what you’d like to work on.

---

Thank you for being a part of the Django Trips journey.  
Together, we can make travel management smarter, faster, and more delightful.

Reach out in you need further assistance.
`admin@destinationpak.com`

Happy coding! ✨
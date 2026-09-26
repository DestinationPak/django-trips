"""Business rules for trips and bookings, independent of any API layer."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.db.models.functions import Greatest
from django.utils import timezone

from django_trips.choices import (
    BookingStatus,
    CustomTripStatus,
    PackageTier,
    TripStatus,
)
from django_trips.models import (
    CustomTrip,
    Trip,
    TripBooking,
    TripItinerary,
    TripPackage,
    TripSchedule,
    TripWishlist,
    get_location_model,
    location_model_supports_hierarchy,
)

TERMS_NOT_ACCEPTED = (
    "You must accept the Terms & Conditions and cancellation policy to book."
)
SCHEDULE_NOT_BOOKABLE = "This departure is not open for booking."
ALREADY_CANCELLED = "Booking is already cancelled."
CANNOT_BE_CANCELLED = "Booking cannot be cancelled."
DRAFT_NOT_IN_PROGRESS = "This custom trip is not being drafted."
DRAFT_NOT_RESTARTABLE = "This custom trip cannot be drafted again right now."
PLAN_NOT_REVISABLE = "Only a drafted custom trip's plan can be revised."
TRIP_M2M_FIELDS = ("locations", "facilities", "trust_badges", "gear", "tags")
REGION_DEPTH = 3


def get_effective_price(package, schedule=None, pickup=None):
    """
    Resolve the final per-person price for a specific package.

    `package.base_price`/`base_child_price` are the tier's stable, absolute
    menu price. `schedule.additional_price`/`additional_child_price` is a
    flat per-date surcharge added on top of it (0 for a regular date, e.g.
    weekend/holiday/peak pricing). `pickup.additional_price` is a flat
    surcharge added to both the adult and child price alike.
    """
    surcharge_adult = schedule.additional_price if schedule else 0
    surcharge_child = schedule.additional_child_price if schedule else 0
    pickup_addl = pickup.additional_price if pickup else 0

    return {
        "price": package.base_price + surcharge_adult + pickup_addl,
        "child_price": package.base_child_price + surcharge_child + pickup_addl,
    }


def validate_trip_booking(trip, schedule, *, package=None, pickup_location=None):
    """
    Raise a ValidationError, keyed by field, if the selection doesn't fit `trip`.

    The schedule and package must belong to `trip`, and the pickup point to
    the schedule. Compares ids only, so it makes no queries.
    """
    if schedule.trip_id != trip.pk:
        raise ValidationError(
            {"schedule": "The schedule must be the same as provided trip"}
        )
    if package and package.trip_id != trip.pk:
        raise ValidationError(
            {"package": "The package must belong to the same trip as the schedule"}
        )
    if pickup_location and pickup_location.schedule_id != schedule.pk:
        raise ValidationError(
            {
                "pickup_location": "The pickup location must belong to the "
                "selected schedule"
            }
        )


def create_trip_booking(  # pylint:disable=too-many-arguments,too-many-locals
    trip,
    schedule,
    *,
    full_name,
    email,
    phone_number,
    target_date,
    adults,
    children=0,
    package=None,
    pickup_location=None,
    message=None,
    terms_accepted=False,
    created_by=None,
):
    """
    Book `adults` + `children` seats on one of `trip`'s schedules.

    Raises a ValidationError keyed by field when the terms weren't accepted,
    the selection doesn't fit the trip, the departure isn't bookable (past,
    or not published), or too few seats are left. The seat
    check and the `booked_seats` update happen under a row lock on the
    schedule, so two concurrent bookings can't both take the last seats.
    Without a package, the trip's Standard package is used, created at a
    zero price if missing.
    """
    if not terms_accepted:
        raise ValidationError({"terms_accepted": TERMS_NOT_ACCEPTED})
    validate_trip_booking(
        trip, schedule, package=package, pickup_location=pickup_location
    )
    total_persons = adults + children

    with transaction.atomic():
        schedule = (
            TripSchedule.objects.bookable().select_for_update().filter(pk=schedule.pk).first()
        )
        if schedule is None:
            raise ValidationError({"schedule": SCHEDULE_NOT_BOOKABLE})
        remaining_seats = schedule.seats_left
        if total_persons > remaining_seats:
            raise ValidationError(
                {"adults": f"Only {remaining_seats} seat(s) left for this schedule."}
            )

        if package is None:
            package, _ = TripPackage.objects.get_or_create(
                trip=schedule.trip,
                name=PackageTier.STANDARD,
                defaults={"base_price": 0, "base_child_price": 0},
            )
        effective = get_effective_price(
            package, schedule=schedule, pickup=pickup_location
        )
        booking = TripBooking.objects.create(
            schedule=schedule,
            package=package,
            pickup_location=pickup_location,
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            target_date=target_date,
            adults=adults,
            children=children,
            message=message,
            terms_accepted=terms_accepted,
            created_by=created_by,
            total_price=effective["price"] * adults
            + effective["child_price"] * children,
        )

        schedule.booked_seats += total_persons
        schedule.save(update_fields=["booked_seats"])

    return booking


def _give_seats_back(booking):
    party = booking.adults + booking.children
    TripSchedule.objects.filter(pk=booking.schedule_id).update(
        booked_seats=Greatest(F("booked_seats"), party) - party
    )


def cancel_trip_booking(booking, *, changed_by=None, reason="", check_cancellable=True):
    """
    Cancel `booking` and give its seats back to the schedule.

    Raises a ValidationError when the booking is already cancelled, or when
    `check_cancellable` is set and its status no longer allows a guest or
    host to cancel. Staff tools pass `check_cancellable=False` to cancel a
    confirmed booking too. `changed_by` and `reason` are recorded on the
    booking's status history. `booked_seats` never drops below zero, even
    for a booking made before seats were counted.
    """
    if BookingStatus.is_cancelled(booking.status):
        raise ValidationError(ALREADY_CANCELLED)
    if check_cancellable and not booking.can_be_cancelled():
        raise ValidationError(CANNOT_BE_CANCELLED)

    with transaction.atomic():
        booking.cancel(changed_by=changed_by, reason=reason)
        _give_seats_back(booking)

    return booking


def delete_trip_booking(booking):
    """Delete `booking`, first giving its seats back unless it was cancelled."""
    with transaction.atomic():
        if not BookingStatus.is_cancelled(booking.status):
            _give_seats_back(booking)
        booking.delete()


def upsert_trip_itinerary(trip, itinerary_data):
    """
    Save `trip`'s itinerary days, matched by `day_index`, in bulk.

    A day already saved is updated in place and a day missing from
    `itinerary_data` is left alone. On a repeated `day_index` the last one
    wins. Returns the category ids the days reference, for the caller to add
    to `trip.categories`.
    """
    itinerary_categories = set()
    items_by_day = {}
    for item in itinerary_data:
        day_index = item.pop("day_index")
        items_by_day[day_index] = item
        if item.get("category"):
            itinerary_categories.add(item["category"])

    existing_by_day = {
        itinerary.day_index: itinerary
        for itinerary in TripItinerary.objects.filter(
            trip=trip, day_index__in=items_by_day.keys()
        )
    }
    to_create = []
    to_update = []
    for day_index, item in items_by_day.items():
        existing = existing_by_day.get(day_index)
        if existing is None:
            to_create.append(TripItinerary(trip=trip, day_index=day_index, **item))
            continue
        for field, value in item.items():
            setattr(existing, field, value)
        to_update.append(existing)

    if to_create:
        TripItinerary.objects.bulk_create(to_create)
    if to_update:
        TripItinerary.objects.bulk_update(
            to_update,
            fields=[
                "title",
                "description",
                "location",
                "category",
                "start_time",
                "end_time",
            ],
        )
    return itinerary_categories


@transaction.atomic
def create_trip(*, created_by=None, itinerary=None, categories=None, **fields):
    """
    Create a trip with its many-to-many links and day-wise itinerary.

    `fields` takes the trip's own fields plus any of `locations`,
    `facilities`, `trust_badges`, `gear` and `tags`. Categories referenced
    by an itinerary day are added to the trip's categories.
    """
    relations = {name: fields.pop(name, None) or [] for name in TRIP_M2M_FIELDS}
    trip = Trip.objects.create(created_by=created_by, **fields)
    for name, values in relations.items():
        getattr(trip, name).set(values)
    trip.categories.set(categories or [])

    itinerary_categories = upsert_trip_itinerary(trip, itinerary or [])
    if itinerary_categories:
        trip.categories.add(*itinerary_categories)
    return trip


@transaction.atomic
def update_trip(trip, *, itinerary=None, categories=None, **fields):
    """
    Update a trip, leaving out anything passed as None.

    A given many-to-many list replaces the current one, except
    `categories`, which is only ever added to: an update must not drop a
    category just because the request omitted it. `itinerary` is upserted
    by day, keeping days it doesn't mention.
    """
    relations = {
        name: fields.pop(name) for name in TRIP_M2M_FIELDS if name in fields
    }
    for attr, value in fields.items():
        setattr(trip, attr, value)
    trip.save()

    for name, values in relations.items():
        if values is not None:
            getattr(trip, name).set(values)
    if categories is not None:
        trip.categories.add(*categories)

    if itinerary is not None:
        itinerary_categories = upsert_trip_itinerary(trip, itinerary)
        if itinerary_categories:
            trip.categories.add(*itinerary_categories)
    return trip


def toggle_trip_wishlist(user, trip):
    """
    Add `trip` to `user`'s wishlist, or remove it if it's already there.

    Returns whether the trip is wished after the toggle.
    """
    entry, created = TripWishlist.objects.get_or_create(user=user, trip=trip)
    if not created:
        entry.delete()
    return created


def create_custom_trip(user, **answers):
    """Validate a traveler's answers and save them as a custom trip being drafted."""
    custom_trip = CustomTrip(user=user, status=CustomTripStatus.DRAFTING, **answers)
    custom_trip.full_clean()
    custom_trip.save()
    return custom_trip


def _region_and_descendant_ids(region):
    ids = [region.pk]
    if not location_model_supports_hierarchy():
        return ids
    frontier = ids
    for _ in range(REGION_DEPTH):
        frontier = list(
            get_location_model()
            .objects.filter(parent_id__in=frontier)
            .values_list("pk", flat=True)
        )
        if not frontier:
            break
        ids.extend(frontier)
    return ids


def get_source_trips(custom_trip, limit=12):
    """
    Return the published host trips a custom trip should be drafted from.

    A trip counts when its destination or one of its stops is the chosen
    region or any place under it, down to towns, since trips are booked to
    towns while travelers pick a region. Itinerary days come prefetched with
    their locations. A custom trip without a region has no source trips.
    """
    if custom_trip.region_id is None:
        return Trip.objects.none()
    location_ids = _region_and_descendant_ids(custom_trip.region)
    return (
        Trip.objects.active()
        .filter(status=TripStatus.PUBLISHED)
        .filter(Q(destination_id__in=location_ids) | Q(locations__in=location_ids))
        .distinct()
        .select_related("destination", "host")
        .prefetch_related(
            Prefetch(
                "itinerary_days",
                queryset=TripItinerary.objects.select_related("location"),
            )
        )[:limit]
    )


def _ensure_drafting(custom_trip):
    if custom_trip.status != CustomTripStatus.DRAFTING:
        raise ValidationError(DRAFT_NOT_IN_PROGRESS)


@transaction.atomic
def mark_custom_trip_drafted(  # pylint:disable=too-many-arguments
    custom_trip,
    *,
    plan,
    title,
    estimate_min,
    estimate_max,
    source_trips,
    metadata=None,
):
    """Save a finished plan on a custom trip being drafted."""
    _ensure_drafting(custom_trip)
    custom_trip.status = CustomTripStatus.DRAFTED
    custom_trip.plan = plan
    custom_trip.title = title
    custom_trip.estimate_min = estimate_min
    custom_trip.estimate_max = estimate_max
    custom_trip.failure_reason = ""
    custom_trip.drafted_at = timezone.now()
    custom_trip.metadata = {**custom_trip.metadata, **(metadata or {})}
    custom_trip.save()
    custom_trip.source_trips.set(source_trips)
    return custom_trip


def mark_custom_trip_failed(custom_trip, reason, metadata=None):
    """Record that drafting a custom trip gave up, and why, for staff."""
    _ensure_drafting(custom_trip)
    custom_trip.status = CustomTripStatus.FAILED
    custom_trip.failure_reason = reason[:255]
    custom_trip.metadata = {**custom_trip.metadata, **(metadata or {})}
    custom_trip.save()
    return custom_trip


def restart_custom_trip_drafting(custom_trip, *, stuck_after):
    """
    Put a custom trip back into drafting so its plan can be written again.

    Allowed after a failed draft, or when a draft has sat in DRAFTING for
    longer than `stuck_after` (a timedelta), which means whatever was
    writing it stopped without recording a result.
    """
    stuck = (
        custom_trip.status == CustomTripStatus.DRAFTING
        and custom_trip.updated_at < timezone.now() - stuck_after
    )
    if custom_trip.status != CustomTripStatus.FAILED and not stuck:
        raise ValidationError(DRAFT_NOT_RESTARTABLE)
    custom_trip.status = CustomTripStatus.DRAFTING
    custom_trip.failure_reason = ""
    custom_trip.save()
    return custom_trip


def revise_custom_trip_plan(  # pylint:disable=too-many-arguments
    custom_trip, *, plan, title, estimate_min, estimate_max, metadata=None
):
    """
    Replace a drafted custom trip's plan with a revised one.

    For changes made after the first draft, such as a traveler asking for a
    shorter day. The trip stays DRAFTED and keeps its `drafted_at`; any
    history of earlier versions is up to the installing project.
    """
    if custom_trip.status != CustomTripStatus.DRAFTED:
        raise ValidationError(PLAN_NOT_REVISABLE)
    custom_trip.plan = plan
    custom_trip.title = title
    custom_trip.estimate_min = estimate_min
    custom_trip.estimate_max = estimate_max
    custom_trip.metadata = {**custom_trip.metadata, **(metadata or {})}
    custom_trip.save()
    return custom_trip

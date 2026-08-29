"""Core data models for the app."""

import random
# pylint:disable=consider-using-from-import,missing-class-docstring,missing-function-docstring,no-member,no-name-in-module
from datetime import UTC, datetime, timedelta

import swapper
from config_models.models import ConfigurationModel
from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.timezone import now
from django_countries.fields import CountryField
from django_extensions.db.models import TimeStampedModel
from taggit.managers import TaggableManager

import django_trips.managers as managers
from django_trips.choices import (
    AvailabilityType,
    BookingStatus,
    FeaturedType,
    LocationType,
    PackageTier,
    ScheduleStatus,
    TripStatus,
)
from django_trips.mixins import SlugMixin


class HostType(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=70, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<HostType: {self.name} slug: {self.slug}>"


class Host(SlugMixin, models.Model):
    """
    Trip host model.

    This model contains the information for the trip hosts who are organizing
    trips.
    """

    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=70, unique=True, null=True, blank=True)

    description = models.TextField(null=True, blank=True)
    type = models.ForeignKey(
        HostType,
        null=True,
        blank=True,
        related_name="hosts",
        on_delete=models.CASCADE,
    )
    cnic = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    mobile = models.CharField(max_length=15, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    cancellation_policy = models.JSONField(default=list, blank=True, null=True)
    refund_policy = models.JSONField(default=list, blank=True, null=True)
    refund_schedule = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="Host-level override for the structured refund-tier schedule "
        "(same shape as CancellationPolicy.refund_schedule). Empty - the "
        "default - falls back to the platform-wide schedule.",
    )

    verified = models.BooleanField(default=False)
    is_active = models.BooleanField(
        default=True,
        help_text="Deactivating a host (via the admin action) also deactivates all "
        "of their trips, hiding them from the public API.",
    )

    objects = managers.HostManager.as_manager()

    class Meta:
        ordering = ["name", "verified"]

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Host: {self.name} slug: {self.slug}>"


class HostRating(models.Model):
    host = models.OneToOneField(
        Host,
        related_name="ratings",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    rating_count = models.SmallIntegerField(default=0, null=True, blank=True)  # 32767
    rated_by = models.SmallIntegerField(default=0, null=True, blank=True)

    def __str__(self):
        return f"{self.host}: {self.rating_count} / {self.rated_by}"

    def __repr__(self):
        return f"<HostRating: {self.rating_count} / {self.rated_by}"


class AbstractLocation(SlugMixin, models.Model):
    """
    Base fields and behavior for a geographical trip location.

    Inherit this to build a custom Location model instead of writing a
    LocationAdapter subclass - you get these fields and methods for
    free and only override what needs to change. See the README's
    "Custom Location model" section for when to reach for this versus
    the adapter.
    """

    name = models.CharField(max_length=30)
    slug = models.SlugField(unique=True, null=True, blank=True)

    travel_tips = models.JSONField(
        default=dict,
        help_text="Structured travel advice containing sections like 'transport', 'safety', etc.",
    )
    lat = models.FloatField(
        null=True,
        blank=True,
        help_text="Latitude coordinate in decimal degrees (WGS84)",
    )
    lon = models.FloatField(
        null=True,
        blank=True,
        help_text="Longitude coordinate in decimal degrees (WGS84)",
    )
    type = models.CharField(
        max_length=100,
        choices=LocationType.choices,
        default=LocationType.CITY,
        help_text="Classification of location type",
    )
    importance = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Numerical importance ranking (higher = more significant)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this location should be shown publicly",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
        help_text="The broader location this belongs to, e.g. a TOWN's parent "
        "PROVINCE. Used to derive `region` for display/grouping.",
    )
    poster_image = models.ImageField(
        upload_to="locations/posters/",
        null=True,
        blank=True,
        help_text="Uploaded poster photo for destination cards. Takes "
        "priority over poster_url when both are set.",
    )
    poster_url = models.URLField(
        null=True,
        blank=True,
        help_text="External poster photo URL, used when poster_image isn't uploaded.",
    )

    objects = managers.LocationQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["name"]
        verbose_name = "Trip Location"
        verbose_name_plural = "Trip Locations"

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Location: {self.name} slug: {self.slug}>"

    @property
    def region(self):
        """
        The broader region/province name this location belongs to, for
        display and grouping (e.g. "Gilgit-Baltistan" for Hunza).

        Returns the parent's name if one is set, this location's own name
        if it is itself a PROVINCE-level location, or None if neither
        applies (e.g. a TOWN with no parent linked yet).
        """
        if self.parent:
            return self.parent.name
        if self.type == LocationType.PROVINCE:
            return self.name
        return None


class Location(AbstractLocation):
    """This package's own default, concrete Location model."""

    class Meta(AbstractLocation.Meta):
        swappable = swapper.swappable_setting("django_trips", "Location")


def get_location_model():
    """Location, or whichever model DJANGO_TRIPS_LOCATION_MODEL swaps it for."""
    return swapper.load_model("django_trips", "Location")


def get_active_locations_queryset():
    """
    The queryset of locations valid to assign on create/update.

    `.active()` is django_trips.Location's own manager method
    (is_active-based), not part of the LocationAdapter contract - a
    swapped-in model isn't guaranteed to define it, so this falls back
    to every row rather than assuming that filter exists elsewhere.
    """
    manager = get_location_model().objects
    if hasattr(manager, "active"):
        return manager.active()
    return manager.all()


def location_model_supports_hierarchy():
    """
    Whether the active Location model has the parent/type fields the
    REGION-rollup search/display features assume (expand_destination_slugs,
    ActiveDestinationsWithSchedulesView, DestinationWithSchedulesSerializer
    .get_schedules).

    True for django_trips' own default Location; not guaranteed for a
    swapped-in model - querying/select_related-ing a field a swapped-in
    model doesn't have raises FieldError, so callers must check this
    first rather than assume the hierarchy exists.
    """
    field_names = {f.name for f in get_location_model()._meta.get_fields()}
    return {"parent", "type"}.issubset(field_names)


class Gear(SlugMixin, models.Model):
    """
    Gear options for a trip.

    This model contains information all the gears that can be used for a trip.
    """

    name = models.CharField(max_length=70, unique=True)
    slug = models.SlugField(max_length=85, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    objects = managers.ActiveQuerySet.as_manager()

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Gear: {self.name} slug: {self.slug}>"


class Facility(SlugMixin, models.Model):
    """
    Trip Facility model

    This model contains information all the available facilities that can be
    provided in a trip.
    """

    name = models.CharField(max_length=70, unique=True)
    slug = models.SlugField(max_length=85, unique=True, null=True, blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon identifier for frontend rendering (e.g. a lucide icon name)",
    )
    is_active = models.BooleanField(default=True)

    objects = managers.ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Facilities"

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Facility: {self.name} slug: {self.slug}>"


class TrustBadge(SlugMixin, models.Model):
    """
    Trip Trust Badge model

    Verifiable credibility signals shown on a trip card (e.g. certified
    guide, free cancellation) — distinct from Facility, which lists what's
    included/provided on the trip rather than making a trust claim about it.
    Optional per trip, same M2M-lookup shape as Facility/Category.
    """

    name = models.CharField(max_length=70, unique=True)
    slug = models.SlugField(max_length=85, unique=True, null=True, blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon identifier for frontend rendering (e.g. a lucide icon name)",
    )
    is_active = models.BooleanField(default=True)

    objects = managers.ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Trust Badges"

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TrustBadge: {self.name} slug: {self.slug}>"


class Category(SlugMixin, models.Model):
    name = models.CharField(max_length=70)
    slug = models.SlugField(max_length=85, unique=True, null=True, blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon identifier for frontend rendering (e.g. a lucide icon name)",
    )
    is_active = models.BooleanField(default=True)

    objects = managers.ActiveQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Category: {self.name} slug: {self.slug}>"


class Trip(SlugMixin, models.Model):
    """
    Trip model

    This model contains the main information that will be presented to
    end users.
    """

    name = models.CharField("Title", max_length=255)
    slug = models.SlugField(max_length=255, unique=True, null=True, blank=True)

    description = models.TextField(
        blank=True,
        null=True,
        help_text="Detailed trip description (html supported).",
    )
    overview = models.TextField(
        blank=True,
        null=True,
        help_text="Short summary displayed in listings (plain text)",
    )
    included = models.TextField(
        blank=True, null=True, help_text="Bullet points of included services/features"
    )
    excluded = models.TextField(
        blank=True, null=True, help_text="Bullet points of excluded services/features"
    )
    add_ons = models.TextField(
        "Additional Information",
        blank=True,
        null=True,
        help_text="Optional upgrades or special offers",
    )
    travel_tips = models.JSONField(
        default=dict,
        help_text="Tips for travelers on this trip, structured as {'section_title': 'content',}",
    )
    requirements = models.JSONField(
        default=dict,
        help_text="User requirements on this trip, Example: {'fitness_level': 'moderate'}",
    )
    child_policy = models.JSONField(default=dict, help_text="Child policy on this trip")
    facilities = models.ManyToManyField(
        Facility, related_name="trips", help_text="Amenities available during the trip"
    )
    trust_badges = models.ManyToManyField(
        TrustBadge,
        related_name="trips",
        blank=True,
        help_text="Verifiable credibility signals for this trip (e.g. certified guide, free cancellation)",
    )
    gear = models.ManyToManyField(
        Gear,
        related_name="trips",
        help_text="Equipment provided or required during the trip.",
    )

    # duration=timedelta(days=5)
    # trip.duration.days
    duration = models.DurationField(
        null=True,
        blank=True,
        help_text="Format: DD HH:MM:SS (e.g., '5 00:00:00' for 5 days)",
    )
    passenger_limit_min = models.PositiveIntegerField(
        default=0, null=True, blank=True, help_text="0 means no minimum requirement"
    )
    passenger_limit_max = models.PositiveIntegerField(
        default=0, null=True, blank=True, help_text="0 means no maximum limit"
    )
    age_limit = models.SmallIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Minimum age requirement (0 = no restriction)",
    )

    departure = models.ForeignKey(
        swapper.get_model_name("django_trips", "Location"),
        null=True,
        blank=True,
        related_name="departure_trips",
        on_delete=models.CASCADE,
        help_text="Starting point of the trip",
    )
    destination = models.ForeignKey(
        swapper.get_model_name("django_trips", "Location"),
        null=True,
        blank=True,
        related_name="destination_trips",
        on_delete=models.CASCADE,
        help_text="Primary destination of the trip",
    )
    locations = models.ManyToManyField(
        swapper.get_model_name("django_trips", "Location"),
        related_name="trips",
        help_text="All locations visited during the trip",
    )
    country = CountryField(
        default="PK", db_index=True, help_text="Primary country where trip operates"
    )

    categories = models.ManyToManyField(
        Category,
        related_name="trips",
        help_text="Classification tags (e.g., 'Adventure', 'Family')",
    )

    # meta includes tinyurl
    metadata = models.JSONField(default=dict, blank=True)

    poster_image = models.ImageField(
        upload_to="trips/posters/",
        null=True,
        blank=True,
        help_text="Uploaded primary listing photo. Takes priority over "
        "poster_url when both are set.",
    )
    poster_url = models.URLField(
        null=True,
        blank=True,
        help_text="External primary listing photo URL, used when poster_image isn't uploaded.",
    )

    featured = models.CharField(
        max_length=20,
        choices=FeaturedType.choices,
        null=True,
        blank=True,
        help_text="Promotional badge shown on the trip (e.g. Bestseller, Popular); left blank if not featured",
    )
    is_pax_required = models.BooleanField(
        default=True, help_text="Whether passenger count must be specified"
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=TripStatus.choices,
        default=TripStatus.PUBLISHED,
        help_text="Editorial state (draft/published) - independent of is_active",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="trips", on_delete=models.CASCADE
    )

    host = models.ForeignKey(
        Host,
        related_name="trips",
        on_delete=models.CASCADE,
        help_text="Organization/guide responsible for the trip",
    )

    tags = TaggableManager(help_text="Comma-separated tags for search/filtering")
    objects = managers.TripQuerySet.as_manager()

    # Transient attribution for the in-flight status change, read by
    # signals.py's post_save receiver - not model fields, so declared here
    # (rather than in a migration) with the same defaults `set_status` uses.
    _status_change_actor = None
    _status_change_reason = ""

    def save(self, *args, **kwargs):
        self.slug = slugify(f"{self.name}-by-{self.host}-for-{self.destination}")
        super().save(*args, **kwargs)

    def set_status(self, status, changed_by=None, reason=""):
        """
        Updates `status` and attributes the resulting TripStatusEvent to
        whoever/whatever caused it - `changed_by=None` (the default) reads
        as a system/automatic change rather than a specific staff action.
        A bare `self.status = ...; self.save()` still logs an event, just
        without that attribution.
        """
        self.status = status
        self._status_change_actor = changed_by
        self._status_change_reason = reason
        self.save()
        return self

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["featured"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Trip: {self.name}, {self.departure} > {self.destination}>"

    @property
    def starting_price(self):
        """
        Cheapest base price among this trip's packages - no `None` fallback
        needed, since `create_standard_package` (signals.py) guarantees every
        trip always has at least one Standard package. Packages aren't
        date-bound, so no active/upcoming schedule filtering applies here.
        """
        return self.packages.order_by("base_price").first().base_price

    def get_absolute_url(self):
        # This is the trips serializers' trip_url field's canonical source too
        # (TripListSerializer/TripDetailSerializer.get_trip_url) - a consuming project
        # that doesn't mount this app's own urls.py under the README's documented
        # "trips-api" namespace (e.g. destipak re-exposing these views under its own
        # namespace instead) overrides DJANGO_TRIPS_URL_NAMESPACE to match.
        namespace = getattr(settings, "DJANGO_TRIPS_URL_NAMESPACE", "trips-api")
        return reverse(f"{namespace}:trip-detail", kwargs={"identifier": self.slug})

    @property
    def cancellation_policy(self):
        """
        Trip's cancellation policy should be given preference over the
        generic host cancellation (all-host-trips) policy.
        """
        return self.host.cancellation_policy or CancellationPolicy.current().description

    @property
    def refund_policy(self):
        """
        Trip's cancellation policy should be given preference over the
        generic host cancellation (all-host-trips) policy.
        """
        return self.host.refund_policy or RefundPolicy.current().description

    @property
    def refund_schedule(self):
        """
        Structured per-timeframe refund tiers backing the cancellation-policy
        timeline UI (e.g. "7+ days: 100% / 3-7 days: 50% / <72hrs: 0%") - same
        host-override-over-platform-default precedence as `cancellation_policy`/
        `refund_policy` above.
        """
        return self.host.refund_schedule or CancellationPolicy.current().refund_schedule

    def create_schedules(self):
        """
        Generates individual trip schedules based on the availability configuration.

        Flow Overview:
        -----------------
            Trip
             └── TripAvailability (type = DAILY, WEEKLY, etc.)
                   └── options = {
                           "date_from": <timestamp>,
                           "end_date": <timestamp>,
                           "is_per_person_price": <bool>
                       }
                   └── price
                   └── available_seats
                       └── create TripSchedule entries for each available date

        Example Structure:
        ------------------
            Trip: "3-Day Hunza Adventure"
                └── TripAvailability:
                        type: DAILY
                        price: 15000
                        options: {
                            "date_from": 01-May-2025,
                            "end_date": 20-May-2025,
                            "is_per_person_price": True
                        }
                        available_seats: 12

                        → create TripSchedules:
                            - 01 May 2025
                            - 02 May 2025
                            - 03 May 2025
                            - ...
                            - 20 May 2025

        Purpose:
        --------
        To pre-fill trip slots for booking on a per-day basis, based on configured
        availability rules. This allows end-users to see specific departure dates
        and book accordingly.

        Returns:
            int: Number of TripSchedule objects created
        """

        availability = self.availabilities.first()

        if not availability or availability.type != AvailabilityType.DAILY:
            return 0

        options = availability.options or {}
        required_keys = {"date_from", "end_date", "is_per_person_price"}
        if not required_keys.issubset(options):  # Required options are missing
            return 0

        try:
            schedule_start = datetime.fromtimestamp(
                options["date_from"] / 1000.0, tz=UTC
            )
            schedule_end = datetime.fromtimestamp(options["end_date"] / 1000.0, tz=UTC)
        except Exception:  # pylint:disable=broad-exception-caught
            return 0

        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # We are not within the scheduling window
        if not schedule_start <= today <= schedule_end:
            return 0

        days_to_generate = min((schedule_end - today).days, 20)
        total_created = 0

        with transaction.atomic():
            for day_offset in range(days_to_generate):
                schedule_date = today + timedelta(days=day_offset)

                _, created = TripSchedule.objects.get_or_create(
                    trip=self,
                    start_date=schedule_date,
                    is_per_person_price=options["is_per_person_price"],
                    defaults={
                        "additional_price": 0,
                        "available_seats": availability.available_seats,
                        "booked_seats": 0,
                    },
                )
                if created:
                    total_created += 1

        return total_created


class TripStatusEvent(models.Model):
    """
    Immutable log entry recording one Trip status transition.

    Written by the `log_trip_status_event` receiver (signals.py) whenever
    `trip_status_changed` fires - a consuming project that wants different
    persistence (or none) can disconnect that receiver and/or connect its
    own; see the docstring on that signal for the override mechanism.
    """

    trip = models.ForeignKey(
        Trip, related_name="status_events", on_delete=models.CASCADE
    )
    old_status = models.CharField(max_length=20, choices=TripStatus.choices)
    new_status = models.CharField(max_length=20, choices=TripStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trip_status_events",
        help_text="Staff user who made this change; blank means system/automatic.",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional context for the change, e.g. 'payment confirmed'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.trip}: {self.old_status} -> {self.new_status}"

    def __repr__(self):
        return f"<TripStatusEvent {self.trip}, {self.old_status} -> {self.new_status}>"


class TripImage(models.Model):
    """
    A single photo in a Trip's gallery/carousel. Ordered by `order`
    (ascending, ties broken by `id`).

    Distinct from `Trip.poster_image`/`poster_url` - the primary listing
    card image is its own dedicated field pair, not derived from this
    gallery.

    Either `image` (an external URL) or `image_upload` (a local file) may
    be set - `image_upload` takes priority when both are, resolved via
    `resolve_media_url` in api/serializers.py.
    """

    trip = models.ForeignKey(Trip, related_name="images", on_delete=models.CASCADE)
    image = models.URLField(help_text="External URL of the photo")
    image_upload = models.ImageField(
        upload_to="trips/images/",
        null=True,
        blank=True,
        help_text="Uploaded photo. Takes priority over `image` (URL) when both are set.",
    )
    alt_text = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(
        default=0, help_text="Display order within the trip's gallery (ascending)"
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.trip}: image #{self.order}"

    def __repr__(self):
        return f"<TripImage trip={self.trip} order={self.order}>"


class TripItinerary(models.Model):
    """
    Represents a day-wise plan or schedule of activities for a Trip.

    Used to describe what happens on each day of a multi-day trip. It can
    include details such as title, description, time slots, location, and
    category (e.g., hiking, sightseeing).
    """

    trip = models.ForeignKey(
        Trip, related_name="itinerary_days", on_delete=models.CASCADE
    )
    day_index = models.SmallIntegerField(default=1)
    title = models.CharField(max_length=150, null=True, blank=True)
    description = models.TextField(default="")
    location = models.ForeignKey(
        swapper.get_model_name("django_trips", "Location"),
        related_name="+",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    category = models.ForeignKey(
        Category, related_name="+", null=True, blank=True, on_delete=models.CASCADE
    )
    start_time = models.DateTimeField(
        null=True,
        blank=True,
    )
    end_time = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"Day:{self.day_index}-{self.trip.name}"

    def __repr__(self):
        return f"<TripItinerary Day:{self.day_index}-{self.trip.name}"

    @property
    def duration(self) -> timedelta:
        """Returns the duration of the itinerary as a timedelta object."""
        return self.end_time - self.start_time

    class Meta:
        ordering = ["trip", "day_index"]
        verbose_name_plural = "Trip Itineraries"
        unique_together = ("trip", "day_index")


class TripAvailability(models.Model):
    """
    Represents the general availability window of a Trip.

    This model defines a time range (start to end date) during which a trip
    is available. It can be configured as DAILY, WEEKLY, FIXED, etc., using
    the `type` field.

    Each availability can include pricing and seating capacity, and is used
    to auto-generate specific `TripSchedule` entries for booking purposes.

    Use Case:
        - Used by `Trip.create_schedules()` to generate multiple TripSchedule
          entries within the defined availability window.
    """

    trip = models.ForeignKey(
        Trip,
        related_name="availabilities",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    price = models.DecimalField(default=0, max_digits=7, decimal_places=0)
    is_per_person_price = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    available_seats = models.PositiveSmallIntegerField(default=0)

    type = models.CharField(
        max_length=100,
        choices=AvailabilityType.choices,
        default=AvailabilityType.MONTHLY,
    )

    options = models.JSONField(default=dict)

    class Meta:
        verbose_name_plural = "Trip Availabilities"
        ordering = ["end_date", "price"]
        unique_together = ("trip", "start_date", "end_date")

    def __str__(self):
        return f"type:{self.type} - price:{self.price} - end_date: {self.start_date}"

    @property
    def is_active(self):
        if self.start_date and self.end_date:
            today = now().date()
            return self.start_date <= today < self.end_date
        return False


class TripSchedule(models.Model):
    """
    Represents a specific scheduled instance of a Trip on a particular date.

    This model allows trips to be booked on specific dates with defined
    pricing and seat availability. It is generated automatically using the
    parent Trip's `TripAvailability` or can be manually created.

    Use Case:
        - Shown to end users as actual bookable trip dates.
        - Supports querying/filtering by date or availability.
    """

    trip = models.ForeignKey(Trip, related_name="schedules", on_delete=models.CASCADE)
    additional_price = models.DecimalField(default=0, max_digits=7, decimal_places=0)
    additional_child_price = models.DecimalField(
        default=0,
        max_digits=7,
        decimal_places=0,
        help_text="Flat per-child surcharge for this specific departure date "
        "(e.g. weekend/holiday/peak pricing), added on top of whichever "
        "package tier is booked - same flat-addition semantic as "
        "TripPickupLocation.additional_price. 0 for a regular date.",
    )
    is_per_person_price = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    available_seats = models.PositiveSmallIntegerField(default=0)
    booked_seats = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices,
        default=ScheduleStatus.DRAFT,
    )
    objects = managers.TripScheduleQuerySet.as_manager()

    def __str__(self):
        return f"{self.trip} - {self.start_date if self.start_date else 'N/A'}"

    def __repr__(self):
        return f"<TripSchedule host={self.start_date} trip={self.trip}>"

    @property
    def is_active(self):
        if self.start_date and self.end_date:
            today = now().date()
            return self.start_date <= today < self.end_date
        return False

    @property
    def seats_left(self):
        return max(self.available_seats - self.booked_seats, 0)


class TripPackage(models.Model):
    """
    Represents a pricing package/tier for a Trip (e.g. Standard, Deluxe, VIP).

    A package carries the tier's stable, absolute menu price. `base_price`/
    `base_child_price` are the full per-person price for that tier,
    independent of any specific departure date - `TripSchedule.additional_price`/
    `additional_child_price` is a flat per-date surcharge added on top of
    whichever package is booked, resolved via `get_effective_price()`
    (`django_trips/services.py`) rather than read off either model alone.
    Every Trip always has exactly one Standard package, auto-created by a
    `post_save` signal (`django_trips/signals.py`) at `base_price=0` until an
    admin sets a real price - so a trip with no extra tiers still has one
    package to book against, with no manual data-entry step required.

    Use Case:
    - Shown to users during booking to choose from trip tiers.
    - Helps support multiple pricing models under the same trip, each with
      its own base price that a schedule's date-specific surcharge is
      layered on top of.
    """

    trip = models.ForeignKey(Trip, related_name="packages", on_delete=models.CASCADE)
    name = models.CharField(
        max_length=20,
        choices=PackageTier.choices,
        default=PackageTier.STANDARD,
    )

    description = models.TextField()
    base_price = models.DecimalField(default=0, max_digits=7, decimal_places=0)
    base_child_price = models.DecimalField(default=0, max_digits=7, decimal_places=0)

    class Meta:
        ordering = ["trip", "base_price"]
        unique_together = ("trip", "name")

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TripPackage {self.name}>"


class TripReview(models.Model):
    """Trip Review Model"""

    trip = models.ForeignKey(Trip, related_name="reviews", on_delete=models.CASCADE)
    meals = models.SmallIntegerField(default=0)
    accommodation = models.SmallIntegerField(default=0)
    transport = models.SmallIntegerField(default=0)
    value_for_money = models.SmallIntegerField(default=0)
    overall = models.SmallIntegerField(default=0)
    comment = models.TextField()
    # User details
    name = models.CharField(max_length=50)
    email = models.EmailField()
    location = models.ForeignKey(
        swapper.get_model_name("django_trips", "Location"),
        null=True,
        blank=True,
        related_name="trip_reviews",
        on_delete=models.SET_NULL,
        help_text="Reviewer's home location, e.g. for display as 'Lahore' "
        "alongside their review.",
    )
    is_verified = models.BooleanField(default=False)
    # timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name}-{self.overall}"

    def __repr__(self):
        return f"<TripReview {self.name}-{self.overall}"


class TripReviewSummary(models.Model):
    """Trip Review Summary Model"""

    trip = models.OneToOneField(
        Trip,
        related_name="review_summary",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    meals = models.FloatField(default=0)
    accommodation = models.FloatField(default=0)
    transport = models.FloatField(default=0)
    value_for_money = models.FloatField(default=0)
    overall = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Trip review summaries"

    def __str__(self):
        return f"{self.trip}-{self.meals}-{self.accommodation}"

    def __repr__(self):
        return f"<TripReviewSummary trip={self.trip}-{self.meals}-{self.accommodation}"


class Testimonial(models.Model):
    """
    Curated, site-wide testimonial for marketing/landing-page display.

    Unlike TripReview (a rating breakdown tied to one specific trip),
    testimonials are freeform quotes used for general social proof and
    aren't required to reference any particular trip.
    """

    quote = models.TextField()
    name = models.CharField(max_length=100)
    location = models.ForeignKey(
        swapper.get_model_name("django_trips", "Location"),
        null=True,
        blank=True,
        related_name="testimonials",
        on_delete=models.SET_NULL,
        help_text="Where the person is from, e.g. 'Lahore'.",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Only verified testimonials should be shown publicly.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this testimonial should be shown publicly.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = managers.TestimonialQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.name}: {self.quote[:50]}"  # pylint:disable=unsubscriptable-object
        )

    def __repr__(self):
        return f"<Testimonial name={self.name} verified={self.is_verified}>"


def default_refund_schedule():
    """Platform-default refund tiers backing the cancellation-policy timeline UI."""
    return [
        {
            "label": "7+ days before departure",
            "min_hours_before_departure": 168,
            "refund_percent": 100,
        },
        {
            "label": "3-7 days before departure",
            "min_hours_before_departure": 72,
            "refund_percent": 50,
        },
        {
            "label": "Less than 72 hours before departure",
            "min_hours_before_departure": 0,
            "refund_percent": 0,
        },
    ]


class CancellationPolicy(ConfigurationModel):
    description = models.TextField()
    refund_schedule = models.JSONField(
        default=default_refund_schedule,
        blank=True,
        help_text="Ordered refund tiers, each a "
        "{'label', 'min_hours_before_departure', 'refund_percent'} dict, "
        "backing the cancellation-policy timeline UI.",
    )

    class Meta:
        verbose_name_plural = "Cancellation policies"

    def __str__(self):
        return str(self.description)

    def __repr__(self):
        return f"<CancellationPolicy description={self.description}>"


class RefundPolicy(ConfigurationModel):
    description = models.TextField()

    def __str__(self):
        return str(self.description)

    def __repr__(self):
        return f"<CancellationPolicy description={self.description}>"


class TripBooking(TimeStampedModel):
    number = models.CharField(
        max_length=16,
        unique=True,
        editable=False,
        help_text="Auto-generated booking reference number",
    )
    otp = models.CharField(
        max_length=4,
        editable=False,
        help_text="Auto-generated 4-digit code, shown once at booking creation. "
        "Paired with `number` as an alternative to `number` + `email` for the "
        "guest booking lookup endpoint.",
    )
    schedule = models.ForeignKey(
        TripSchedule, related_name="bookings", on_delete=models.CASCADE
    )
    package = models.ForeignKey(
        "TripPackage",
        related_name="bookings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Pricing package/tier selected for this booking. Defaults to "
        "the trip's Standard package when not supplied at creation time.",
    )
    pickup_location = models.ForeignKey(
        "TripPickupLocation",
        related_name="bookings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Pickup point selected for this booking, if any. Must be one "
        "of the pickup points offered on the booking's own schedule.",
    )
    total_price = models.DecimalField(
        default=0,
        max_digits=10,
        decimal_places=0,
        help_text="Computed total price for this booking (effective adult price "
        "times adults, plus effective child price times children), stored at "
        "creation time.",
    )

    full_name = models.CharField(
        max_length=255, help_text="Full name of the primary contact person"
    )
    email = models.EmailField(
        help_text="Email address for booking confirmations and updates"
    )
    phone_number = models.CharField(
        max_length=30, help_text="Contact phone number with country code"
    )
    adults = models.PositiveIntegerField(
        default=1,
        help_text="Number of adult participants",
    )
    children = models.PositiveIntegerField(
        default=0,
        help_text="Number of child participants",
    )
    target_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Preferred date/time for the trip.",
    )

    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        help_text="Current status of the booking",
    )
    message = models.TextField(
        null=True, blank=True, help_text="Special requests or additional information"
    )
    terms_accepted = models.BooleanField(
        default=False,
        help_text="Guest agreed to the Terms & Conditions and cancellation policy at booking time",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="bookings",
        on_delete=models.CASCADE,
        help_text="User who created this booking (null for guest bookings)",
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when booking was cancelled (null if active)",
    )
    objects = managers.TripBookingManager.as_manager()

    class Meta:
        verbose_name = "Trip Booking"
        verbose_name_plural = "Trip Bookings"
        ordering = ("target_date", "-created")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["schedule"]),
        ]

    def __str__(self):
        return f"<TripBooking {self.full_name}, {self.target_date}, {self.status}/>"

    def __repr__(self):
        return f"<TripBooking - {self.full_name}, {self.target_date}, {self.status}/>"

    def save(self, **kwargs):
        if not self.number:
            self.number = self.generate_booking_number()
        if not self.otp:
            self.otp = self.generate_otp()
        super().save(**kwargs)

    # Transient attribution for the in-flight status change, read by
    # signals.py's post_save receiver - not model fields, so declared here
    # (rather than in a migration) with the same defaults `set_status` uses.
    _status_change_actor = None
    _status_change_reason = ""

    def set_status(self, status, changed_by=None, reason=""):
        """
        Updates `status` and attributes the resulting BookingStatusEvent to
        whoever/whatever caused it - `changed_by=None` (the default) reads
        as a system/automatic change rather than a specific staff action.
        A bare `self.status = ...; self.save()` still logs an event, just
        without that attribution.
        """
        self.status = status
        self._status_change_actor = changed_by
        self._status_change_reason = reason
        self.save()
        return self

    def cancel(self, changed_by=None, reason=""):
        self.cancelled_at = timezone.now()
        return self.set_status(
            BookingStatus.CANCELLED, changed_by=changed_by, reason=reason
        )

    def can_be_cancelled(self):
        return BookingStatus.can_be_cancelled(self.status)

    @classmethod
    def generate_booking_number(cls):
        """
        DPT00000107
        DPT00000284
        DPT00000332
        """
        prefix = "DPT"
        count = cls.objects.count() + 1
        padded_number = f"{count:06d}"  # e.g., 000123

        # Generate 2 random digits
        suffix = f"{random.randint(0, 99):02d}"

        return f"{prefix}{padded_number}{suffix}"

    @classmethod
    def generate_otp(cls):
        """A random 4-digit code, e.g. "0492". Not checked for uniqueness -
        it's only ever looked up together with `number`, which is unique."""
        return f"{random.randint(0, 9999):04d}"


class BookingStatusEvent(models.Model):
    """
    Immutable log entry recording one TripBooking status transition.

    Written by the `log_booking_status_event` receiver (signals.py) whenever
    `booking_status_changed` fires - a consuming project that wants different
    persistence (or none) can disconnect that receiver and/or connect its
    own; see the docstring on that signal for the override mechanism.
    """

    booking = models.ForeignKey(
        TripBooking, related_name="status_events", on_delete=models.CASCADE
    )
    old_status = models.CharField(max_length=20, choices=BookingStatus.choices)
    new_status = models.CharField(max_length=20, choices=BookingStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="booking_status_events",
        help_text="Staff user who made this change; blank means system/automatic.",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional context for the change, e.g. 'advance payment received'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.booking}: {self.old_status} -> {self.new_status}"

    def __repr__(self):
        return f"<BookingStatusEvent {self.booking}, {self.old_status} -> {self.new_status}>"


class TripWishlist(models.Model):
    """
    A user's saved/wishlisted trip (e.g. a "heart" toggle in a trip listing).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="wishlisted_trips",
        on_delete=models.CASCADE,
    )
    trip = models.ForeignKey(
        Trip, related_name="wishlisted_by", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "trip")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.trip}"

    def __repr__(self):
        return f"<TripWishlist user={self.user} trip={self.trip}>"


class TripPickupLocation(models.Model):
    """A pickup point offered for a specific trip departure (`TripSchedule`)."""

    schedule = models.ForeignKey(
        TripSchedule, related_name="pickup_locations", on_delete=models.CASCADE
    )
    location = models.ForeignKey(
        swapper.get_model_name("django_trips", "Location"), on_delete=models.CASCADE
    )
    additional_price = models.SmallIntegerField(default=0)

    def __str__(self):
        return str(self.location)

    def __repr__(self):
        return f"<TripPickupLocation schedule={self.schedule}-{self.location}>"

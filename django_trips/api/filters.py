from datetime import timedelta

import django_filters as filters
from django.db.models import Q

from django_trips.choices import LocationType, ScheduleStatus
from django_trips.models import (
    Trip,
    TripBooking,
    TripPackage,
    TripSchedule,
    get_location_model,
    location_model_supports_hierarchy,
)


def expand_destination_slugs(slugs):
    """
    A REGION-type destination (e.g. 'galiyat') has no trips of its own -
    trips are booked to its child towns (e.g. 'nathia-gali'). Searching by
    the region name is how travelers actually search (see Location.parent/
    Location.region), so filtering by a region's slug must also match trips
    destined for any of its children, not just an exact slug match.

    Scoped to parent__type=REGION specifically - a CITY with children (e.g.
    Skardu with Shangrila) doesn't roll its children up; only a REGION does.

    This is django_trips' own Location hierarchy concept (parent/type),
    not part of the adapter contract - it only rolls up region children
    when DJANGO_TRIPS_LOCATION_MODEL is unswapped (the default model);
    a swapped-in model without parent/type just gets an exact-slug match.
    """
    if not location_model_supports_hierarchy():
        return set(slugs)
    return set(slugs) | set(
        get_location_model()
        .objects.filter(parent__slug__in=slugs, parent__type=LocationType.REGION)
        .values_list("slug", flat=True)
    )


class TimedeltaFromDaysFilter(filters.NumberFilter):
    def filter(self, qs, value):
        if value is not None:
            try:
                value = timedelta(days=float(value))
            except (ValueError, TypeError):
                return qs.none()
        return super().filter(qs, value)


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class TripBaseFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    destination = CharInFilter(
        field_name="destination__slug",
        lookup_expr="in",
        method="filter_destination",
        help_text="Filter trips by a list of destination slugs, e.g. "
        "?destination=hunza,skardu. A REGION-type slug (e.g. 'galiyat') also "
        "matches trips destined for any of that region's child locations "
        "(e.g. 'nathia-gali').",
    )
    duration_from = TimedeltaFromDaysFilter(field_name="duration", lookup_expr="gte")
    duration_to = TimedeltaFromDaysFilter(field_name="duration", lookup_expr="lte")

    class Meta:
        model = Trip
        fields = []

    def filter_destination(self, queryset, _name, value):
        if not value:
            return queryset
        return queryset.filter(destination__slug__in=expand_destination_slugs(value))


class TripFilter(TripBaseFilter):
    """
    Filter trips by name, destination, duration, category, price range,
    and/or date range.

    price_from/price_to match against a trip's packages directly - a
    package's base_price is date-independent, so no cross-schedule
    combination concern applies there. date_from/date_to are still combined
    into a single query against TripSchedule rather than independent
    per-field filters: since a trip can have many schedules, filtering each
    condition separately (as django-filter would by default) can match a
    trip via two *different* schedules (e.g. a cheap-but-past one and an
    expensive-but-future one) even though no single schedule satisfies both.
    filter_queryset() below implements both halves.
    """

    category = CharInFilter(
        field_name="categories__slug",
        lookup_expr="in",
        help_text="Filter trips by a list of category slugs, e.g. ?category=hiking,camping",
    )
    host = CharInFilter(
        field_name="host__slug",
        lookup_expr="in",
        help_text="Filter trips by a list of host slugs, e.g. ?host=blue-sky-tours,acme",
    )
    trust_badge = CharInFilter(
        field_name="trust_badges__slug",
        lookup_expr="in",
        help_text="Filter trips by a list of trust badge slugs, e.g. ?trust_badge=certified-guide",
    )
    verified_host = filters.BooleanFilter(
        field_name="host__verified",
        help_text="Filter trips by whether their host is verified, e.g. ?verified_host=true",
    )
    price_from = filters.NumberFilter(
        method="filter_noop",
        help_text="Filter trips with a package priced at or above this value "
        "(still requires a published schedule to be bookable).",
    )
    price_to = filters.NumberFilter(
        method="filter_noop",
        help_text="Filter trips with a package priced at or below this value "
        "(still requires a published schedule to be bookable).",
    )
    date_from = filters.DateFilter(
        method="filter_noop",
        help_text="Filter trips with a published schedule starting on or "
        "after this date (YYYY-MM-DD).",
    )
    date_to = filters.DateFilter(
        method="filter_noop",
        help_text="Filter trips with a published schedule ending on or "
        "before this date (YYYY-MM-DD).",
    )

    class Meta(TripBaseFilter.Meta):
        model = Trip
        fields = []

    def filter_noop(self, queryset, _name, _value):
        """Actual filtering for these fields happens once, combined, in filter_queryset()."""
        return queryset

    def filter_queryset(self, queryset):
        price_constraints = Q()
        has_price_constraint = False
        for field_name, lookup in (
            ("price_from", "base_price__gte"),
            ("price_to", "base_price__lte"),
        ):
            value = self.form.cleaned_data.get(field_name)
            if value not in (None, ""):
                price_constraints &= Q(**{lookup: value})
                has_price_constraint = True

        if has_price_constraint:
            matching_trip_ids = TripPackage.objects.filter(
                price_constraints
            ).values_list("trip_id", flat=True)
            queryset = queryset.filter(pk__in=matching_trip_ids)
            # A price match alone isn't enough - still require an actual
            # bookable schedule, preserving today's implicit guarantee that
            # browsing by budget never surfaces an unbookable trip.
            queryset = queryset.filter(
                schedules__status=ScheduleStatus.PUBLISHED
            ).distinct()

        schedule_constraints = Q(status=ScheduleStatus.PUBLISHED)
        has_schedule_constraint = False
        for field_name, lookup in (
            ("date_from", "start_date__gte"),
            ("date_to", "end_date__lte"),
        ):
            value = self.form.cleaned_data.get(field_name)
            if value not in (None, ""):
                schedule_constraints &= Q(**{lookup: value})
                has_schedule_constraint = True

        if has_schedule_constraint:
            matching_trip_ids = TripSchedule.objects.filter(
                schedule_constraints
            ).values_list("trip_id", flat=True)
            queryset = queryset.filter(pk__in=matching_trip_ids)

        return super().filter_queryset(queryset)


class UpcomingTripsFilter(filters.FilterSet):
    """
    Filter upcoming trips by name, price range, date range, destination slug,
    and trip duration range (in days).
    """

    name = filters.CharFilter(
        field_name="trip__name",
        lookup_expr="icontains",
        help_text="Filter trips whose name contains this value (case-insensitive).",
    )
    price_from = filters.NumberFilter(
        field_name="price",
        lookup_expr="gte",
        help_text="Filter trips with a fully resolved price (cheapest package's "
        "base_price plus this schedule's surcharge) greater than or equal to "
        "this value.",
    )
    price_to = filters.NumberFilter(
        field_name="price",
        lookup_expr="lte",
        help_text="Filter trips with a fully resolved price (cheapest package's "
        "base_price plus this schedule's surcharge) less than or equal to "
        "this value.",
    )
    # "%Y-%m-%d"
    date_from = filters.DateFilter(
        field_name="start_date",
        lookup_expr="gte",
        help_text="Filter trips starting on or after this date (YYYY-MM-DD).",
    )
    date_to = filters.DateFilter(
        field_name="end_date",
        lookup_expr="lte",
        help_text="Filter trips ending on or before this date (YYYY-MM-DD).",
    )
    destination = CharInFilter(
        field_name="trip__destination__slug",
        lookup_expr="in",
        method="filter_destination",
        help_text="Filter trips by a list of destination slugs, e.g. "
        "?destination=hunza,skardu. A REGION-type slug (e.g. 'galiyat') also "
        "matches trips destined for any of that region's child locations "
        "(e.g. 'nathia-gali').",
    )
    duration_from = TimedeltaFromDaysFilter(
        field_name="trip__duration",
        lookup_expr="gte",
        help_text="Filter trips with duration greater than or equal to this many days.",
    )
    duration_to = TimedeltaFromDaysFilter(
        field_name="trip__duration",
        lookup_expr="lte",
        help_text="Filter trips with duration less than or equal to this many days.",
    )

    class Meta:
        model = TripSchedule
        fields = [
            "name",
            "price_from",
            "price_to",
            "date_from",
            "date_to",
            "destination",
            "duration_from",
            "duration_to",
        ]

    def filter_destination(self, queryset, _name, value):
        if not value:
            return queryset
        return queryset.filter(trip__destination__slug__in=expand_destination_slugs(value))


class TripBookingFilterSet(filters.FilterSet):
    target_date_after = filters.DateTimeFilter(
        field_name="target_date",
        lookup_expr="gte",
        help_text="Include trip bookings targeted on or after this datetime.",
    )
    target_date_before = filters.DateTimeFilter(
        field_name="target_date",
        lookup_expr="lte",
        help_text="Include trip bookings targeted on or before this datetime.",
    )

    class Meta:
        model = TripBooking
        fields = [
            "schedule",
            "schedule__trip",
            "target_date_before",
            "target_date_after",
            "adults",
            "children",
        ]

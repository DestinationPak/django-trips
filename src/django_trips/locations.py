"""
Queries over the Location hierarchy that trips are booked to.

Location is swappable, so these are functions rather than manager methods:
a swapped-in model's manager is not this app's to extend. The region
rollup only applies to a model with this app's `parent`/`type` hierarchy
(`location_model_supports_hierarchy()`); any other model gets exact matches.
"""

from django.db.models import Count, Q

from django_trips.choices import LocationType
from django_trips.models import (
    Trip,
    get_active_locations_queryset,
    get_location_model,
    location_model_supports_hierarchy,
)


def expand_destination_slugs(slugs):
    """
    Return `slugs` plus the slugs of every child of a REGION among them.

    Trips are booked to towns, not regions (a trip goes to "nathia-gali",
    not "galiyat"), but travelers search by region, so a region must match
    its children's trips. Only a REGION rolls up; a CITY with children
    (Skardu with Shangrila) does not.
    """
    if not location_model_supports_hierarchy():
        return set(slugs)
    return set(slugs) | set(
        get_location_model()
        .objects.filter(parent__slug__in=slugs, parent__type=LocationType.REGION)
        .values_list("slug", flat=True)
    )


def destinations_with_trip_counts():
    """
    Return active locations that have trips, annotated with `trips_count`.

    A REGION counts its children's trips too, so it is listed even when no
    trip is booked to the region itself. Only REGION rolls up, not PROVINCE,
    which would otherwise turn into a catch-all for every trip inside it.
    Ordered busiest first.
    """
    queryset = get_active_locations_queryset()
    active_trips = Count(
        "destination_trips", filter=Q(destination_trips__is_active=True), distinct=True
    )
    if not location_model_supports_hierarchy():
        return (
            queryset.filter(destination_trips__isnull=False)
            .annotate(trips_count=active_trips)
            .distinct()
            .order_by("-trips_count", "name")
        )
    return (
        queryset.filter(
            Q(destination_trips__isnull=False)
            | Q(type=LocationType.REGION, children__destination_trips__isnull=False)
        )
        .annotate(
            trips_count=active_trips
            + Count(
                "children__destination_trips",
                filter=Q(
                    children__destination_trips__is_active=True,
                    type=LocationType.REGION,
                ),
                distinct=True,
            )
        )
        .distinct()
        .order_by("-trips_count", "name")
    )


def trips_booked_to(location):
    """
    Return the trips destined for `location`, or for its children when it's a REGION.

    The same rollup `destinations_with_trip_counts()` counts, so a region's
    trip count and its trips always agree.
    """
    destinations = Q(destination=location)
    if location_model_supports_hierarchy() and location.type == LocationType.REGION:
        destinations |= Q(destination__parent=location)
    return Trip.objects.filter(destinations)

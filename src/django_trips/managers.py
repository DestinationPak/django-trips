from django.db import models
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Q
from django.utils import timezone
from django.utils.timezone import now


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class TripCountQuerySetMixin:
    """Adds `with_trip_counts()` to a queryset of a model trips link to as `trips`."""

    def with_trip_counts(self):
        """Annotate each row's active-trip count as `trips_count`, busiest first."""
        return self.annotate(
            trips_count=Count("trips", filter=Q(trips__is_active=True), distinct=True)
        ).order_by("-trips_count", "name")


class TripTaxonomyQuerySet(TripCountQuerySetMixin, ActiveQuerySet):
    """Queryset for the lookup models a trip is tagged with, e.g. categories."""


class LocationQuerySet(ActiveQuerySet):
    pass


class TripQuerySet(ActiveQuerySet):
    def active(self):
        return super().active().filter(host__verified=True)

    def with_price(self):
        """
        Annotate each trip's cheapest package price as `price`.

        The name is `price` so `?ordering=price` can sort on it; it can't be
        `starting_price`, which is a model property with no setter. The
        aggregate drops `Meta.ordering`, so it is re-applied here to keep the
        row order stable.
        """
        return (
            self.annotate(price=Min("packages__base_price"))
            .distinct()
            .order_by(*self.model._meta.ordering)  # pylint:disable=protected-access
        )


class TestimonialQuerySet(ActiveQuerySet):
    def verified(self):
        return self.filter(is_verified=True)


class TripScheduleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(start_date__lte=now(), end_date__gte=now())

    def upcoming(self):
        return self.filter(start_date__gte=now())

    def with_price(self):
        """Annotate each schedule's price, its trip's cheapest package plus this date's surcharge."""
        return self.annotate(
            trip_min_base_price=Min("trip__packages__base_price")
        ).annotate(
            price=ExpressionWrapper(
                F("trip_min_base_price") + F("additional_price"),
                output_field=DecimalField(),
            )
        )


class HostManager(TripCountQuerySetMixin, models.QuerySet):
    def active(self):
        return self.filter(verified=True)


class TripBookingManager(models.QuerySet):
    def active(self):
        return self.filter(target_date__gt=timezone.now())

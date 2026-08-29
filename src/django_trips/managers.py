from django.db import models
from django.utils import timezone
from django.utils.timezone import now


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class LocationQuerySet(ActiveQuerySet):
    pass


class TripQuerySet(ActiveQuerySet):
    def active(self):
        return super().active().filter(host__verified=True)


class TestimonialQuerySet(ActiveQuerySet):
    def verified(self):
        return self.filter(is_verified=True)


class TripScheduleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(start_date__lte=now(), end_date__gte=now())

    def upcoming(self):
        return self.filter(start_date__gte=now())


class HostManager(models.QuerySet):
    def active(self):
        return self.filter(verified=True)


class TripBookingManager(models.QuerySet):
    def active(self):
        return self.filter(target_date__gt=timezone.now())

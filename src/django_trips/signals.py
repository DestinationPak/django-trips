"""Signal receivers for django_trips."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import Signal, receiver

from django_trips.choices import PackageTier
from django_trips.models import BookingStatusEvent, Trip, TripBooking, TripPackage, TripStatusEvent

#: Sent after a Trip's `status` field actually changes value on save
#: (never on creation, since there's no prior status to transition from).
#: Kwargs: `trip`, `old_status`, `new_status`, `changed_by`, `reason`.
#: `changed_by`/`reason` come from `Trip.set_status()`; both are blank when
#: the status was set directly (`trip.status = ...; trip.save()`) - that
#: reads as a system/automatic change with no further context.
#:
#: This is a plain, public Django signal - the intended extension point for
#: a consuming project that wants different behaviour than the library's own
#: default (`log_trip_status_event` below), without forking this file:
#:   - to replace it: disconnect the default receiver
#:     (`trip_status_changed.disconnect(log_trip_status_event, sender=Trip)`)
#:     and connect your own.
#:   - to add to it (e.g. send a notification): just connect another
#:     receiver; the default logging still runs.
trip_status_changed = Signal()


@receiver(post_save, sender=Trip)
def create_standard_package(sender, instance, created, **kwargs):  # pylint:disable=unused-argument
    """
    Every Trip must always have exactly one Standard TripPackage, starting at
    base_price=0 until an admin sets a real price. get_or_create keeps this
    idempotent regardless of how many times/ways a Trip ends up saved.
    """
    if not created:
        return
    TripPackage.objects.get_or_create(
        trip=instance,
        name=PackageTier.STANDARD,
        defaults={"base_price": 0, "base_child_price": 0},
    )


@receiver(pre_save, sender=Trip)
def _capture_previous_trip_status(sender, instance, **kwargs):  # pylint:disable=unused-argument
    """
    Stashes the pre-save status on the instance, since Django has no
    built-in "did this field change" hook - the paired post_save receiver
    below compares against this to detect an actual transition.
    """
    instance._previous_status = (  # pylint:disable=protected-access
        sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=Trip)
def _dispatch_trip_status_changed(sender, instance, created, **kwargs):  # pylint:disable=unused-argument
    """Fires `trip_status_changed` once the new status is committed."""
    previous_status = getattr(instance, "_previous_status", None)
    # Consume the attribution set by set_status() (if any) so a later bare
    # `trip.status = ...; trip.save()` on this same instance doesn't
    # inherit it.
    changed_by = instance._status_change_actor  # pylint:disable=protected-access
    reason = instance._status_change_reason  # pylint:disable=protected-access
    instance._status_change_actor = None  # pylint:disable=protected-access
    instance._status_change_reason = ""  # pylint:disable=protected-access

    if created or previous_status is None or previous_status == instance.status:
        return
    trip_status_changed.send(
        sender=sender,
        trip=instance,
        old_status=previous_status,
        new_status=instance.status,
        changed_by=changed_by,
        reason=reason,
    )


@receiver(trip_status_changed, sender=Trip)
def log_trip_status_event(  # pylint:disable=unused-argument,too-many-arguments
    sender, trip, old_status, new_status, *, changed_by=None, reason="", **kwargs
):
    """Default handling for `trip_status_changed`: logs a TripStatusEvent."""
    TripStatusEvent.objects.create(
        trip=trip,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason,
    )


#: Sent after a TripBooking's `status` field actually changes value on save
#: (never on creation, since there's no prior status to transition from).
#: Kwargs: `booking`, `old_status`, `new_status`, `changed_by`, `reason`.
#: `changed_by`/`reason` come from `TripBooking.set_status()` (used by
#: `cancel()` too); both are blank when the status was set directly
#: (`booking.status = ...; booking.save()`) - that reads as a
#: system/automatic change with no further context.
#:
#: Same override mechanism as `trip_status_changed` above - disconnect
#: `log_booking_status_event` to replace the default DB logging, or just
#: connect another receiver to add to it.
booking_status_changed = Signal()


@receiver(pre_save, sender=TripBooking)
def _capture_previous_booking_status(sender, instance, **kwargs):  # pylint:disable=unused-argument
    """Mirrors `_capture_previous_trip_status` for TripBooking."""
    instance._previous_status = (  # pylint:disable=protected-access
        sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=TripBooking)
def _dispatch_booking_status_changed(sender, instance, created, **kwargs):  # pylint:disable=unused-argument
    """Fires `booking_status_changed` once the new status is committed."""
    previous_status = getattr(instance, "_previous_status", None)
    # Consume the attribution set by set_status() (if any) so a later bare
    # `booking.status = ...; booking.save()` on this same instance doesn't
    # inherit it.
    changed_by = instance._status_change_actor  # pylint:disable=protected-access
    reason = instance._status_change_reason  # pylint:disable=protected-access
    instance._status_change_actor = None  # pylint:disable=protected-access
    instance._status_change_reason = ""  # pylint:disable=protected-access

    if created or previous_status is None or previous_status == instance.status:
        return
    booking_status_changed.send(
        sender=sender,
        booking=instance,
        old_status=previous_status,
        new_status=instance.status,
        changed_by=changed_by,
        reason=reason,
    )


@receiver(booking_status_changed, sender=TripBooking)
def log_booking_status_event(  # pylint:disable=unused-argument,too-many-arguments
    sender, booking, old_status, new_status, *, changed_by=None, reason="", **kwargs
):
    """Default handling for `booking_status_changed`: logs a BookingStatusEvent."""
    BookingStatusEvent.objects.create(
        booking=booking,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason,
    )

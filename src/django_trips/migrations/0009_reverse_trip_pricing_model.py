"""
Reverse the trip pricing model (see docs/TripPricingModelReversalPlan.md in
the destipak root repo): TripPackage keeps its original, always-absolute
`base_price`/`base_child_price` (unchanged since this app's initial
migration - no rename needed), and TripSchedule's `price`/`child_price`
become a flat per-date surcharge (`additional_price`/`additional_child_price`)
added on top of whichever package tier is booked, resolved via
`get_effective_price()` (`django_trips/services.py`).

Schema (rename) and data (rebase) are split into two operations *within*
this one migration rather than two migration files - `apps.get_model()` in
`rebase_schedule_surcharges` below already sees the renamed field, since
Django migration operations run sequentially - so there's no ordering
hazard to guard against by splitting further.
"""

from django.db import migrations, models
from django.db.models import Q
from django.utils.timezone import now

STANDARD = "STANDARD"


def backfill_standard_packages(apps, schema_editor):
    """Every Trip must have a Standard package to book against - the
    `create_standard_package` post_save signal (`signals.py`) guarantees
    this going forward, but doesn't help Trips that already existed before
    that signal was introduced."""
    Trip = apps.get_model("django_trips", "Trip")
    TripPackage = apps.get_model("django_trips", "TripPackage")

    trips_missing_standard = Trip.objects.exclude(packages__name=STANDARD)
    for trip in trips_missing_standard.iterator():
        TripPackage.objects.get_or_create(
            trip=trip,
            name=STANDARD,
            defaults={"base_price": 0, "base_child_price": 0},
        )


def get_reference_schedule(trip_id, TripSchedule):
    n = now()
    return (
        TripSchedule.objects.filter(trip_id=trip_id)
        .filter(Q(start_date__lte=n, end_date__gte=n) | Q(start_date__gte=n))
        .order_by("additional_price")  # post-rename field name; still holds the OLD absolute price at this point
        .first()
    )


def rebase_schedule_surcharges(apps, schema_editor):
    """
    `TripSchedule.additional_price`/`additional_child_price` currently still
    hold the OLD absolute per-date price (RenameField preserves values,
    it doesn't recompute them). For each trip, anchor on the cheapest
    active-or-upcoming schedule - the same reference `Trip.starting_price`/
    `get_effective_price()` used pre-reversal - and rebase every schedule
    relative to it: the anchor schedule itself lands at exactly 0 ("no
    surcharge"), others become a surcharge/discount relative to it.

    Scoped to *active-or-upcoming* schedules specifically, not literally the
    cheapest of all schedules: a stale/sold-out schedule can be cheaper than
    anything currently bookable, which would otherwise anchor a trip's
    effective starting price at a number nobody can actually book.

    Trips with packages but no active/upcoming schedule to anchor against
    are left untouched and logged - there's no reference price to rebase
    against, so touching them would produce an arbitrary surcharge value.
    """
    Trip = apps.get_model("django_trips", "Trip")
    TripSchedule = apps.get_model("django_trips", "TripSchedule")

    skipped_trip_ids = []

    for trip in Trip.objects.prefetch_related("packages", "schedules").iterator(
        chunk_size=100
    ):
        if not trip.packages.exists():
            continue

        reference_schedule = get_reference_schedule(trip.id, TripSchedule)
        if not reference_schedule:
            skipped_trip_ids.append(trip.id)
            continue

        reference_adult = reference_schedule.additional_price  # old absolute value
        reference_child = reference_schedule.additional_child_price

        for schedule in trip.schedules.all():
            schedule.additional_price = schedule.additional_price - reference_adult
            schedule.additional_child_price = (
                schedule.additional_child_price - reference_child
            )
            schedule.save(
                update_fields=["additional_price", "additional_child_price"]
            )

    if skipped_trip_ids:
        print(
            f"\n[0009_reverse_trip_pricing_model] {len(skipped_trip_ids)} trip(s) had "
            "packages but no active/upcoming schedule to anchor against - left "
            f"untouched: {skipped_trip_ids}\n"
        )


def noop_reverse(apps, schema_editor):
    """Irreversible: the pre-rebase absolute prices aren't recoverable once rebased."""


class Migration(migrations.Migration):

    dependencies = [
        ("django_trips", "0008_tripbooking_party_composition"),
    ]

    operations = [
        migrations.RenameField(
            model_name="tripschedule",
            old_name="price",
            new_name="additional_price",
        ),
        migrations.RenameField(
            model_name="tripschedule",
            old_name="child_price",
            new_name="additional_child_price",
        ),
        migrations.AlterField(
            model_name="tripschedule",
            name="additional_child_price",
            field=models.DecimalField(
                decimal_places=0,
                default=0,
                help_text="Flat per-child surcharge for this specific departure "
                "date (e.g. weekend/holiday/peak pricing), added on top of "
                "whichever package tier is booked - same flat-addition semantic "
                "as TripPickupLocation.additional_price. 0 for a regular date.",
                max_digits=7,
            ),
        ),
        migrations.AlterModelOptions(
            name="trippackage",
            options={"ordering": ["trip", "base_price"]},
        ),
        migrations.RunPython(backfill_standard_packages, noop_reverse),
        migrations.RunPython(rebase_schedule_surcharges, noop_reverse),
    ]

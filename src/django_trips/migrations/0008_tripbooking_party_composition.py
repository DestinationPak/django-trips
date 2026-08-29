import django.db.models.deletion
from django.db import migrations, models


def backfill_adults(apps, schema_editor):
    """Existing bookings only ever recorded a single head-count - carry that
    over as `adults` (with `children` left at its default of 0) rather than
    guessing a split that was never captured."""
    TripBooking = apps.get_model("django_trips", "TripBooking")
    TripBooking.objects.update(adults=models.F("number_of_persons"))


def noop_reverse(apps, schema_editor):
    """Irreversible: adults/children can't be recombined into a single count
    without knowing which rows already had children backfilled to 0 by
    default vs. genuinely booked with none."""


class Migration(migrations.Migration):

    dependencies = [
        ("django_trips", "0007_tripbooking_terms_accepted"),
    ]

    operations = [
        migrations.AddField(
            model_name="tripbooking",
            name="package",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="Pricing package/tier selected for this booking. "
                "Defaults to the trip's Standard package when not supplied "
                "at creation time.",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="django_trips.trippackage",
            ),
        ),
        migrations.AddField(
            model_name="tripbooking",
            name="total_price",
            field=models.DecimalField(
                default=0,
                max_digits=10,
                decimal_places=0,
                help_text="Computed total price for this booking (effective "
                "adult price times adults, plus effective child price times "
                "children), stored at creation time.",
            ),
        ),
        migrations.AddField(
            model_name="tripbooking",
            name="adults",
            field=models.PositiveIntegerField(
                default=1, help_text="Number of adult participants"
            ),
        ),
        migrations.AddField(
            model_name="tripbooking",
            name="children",
            field=models.PositiveIntegerField(
                default=0, help_text="Number of child participants"
            ),
        ),
        migrations.RunPython(backfill_adults, noop_reverse),
        migrations.RemoveField(
            model_name="tripbooking",
            name="number_of_persons",
        ),
    ]

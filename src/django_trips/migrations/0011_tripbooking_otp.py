import random

from django.db import migrations, models


def backfill_otp(apps, schema_editor):
    TripBooking = apps.get_model("django_trips", "TripBooking")
    for booking in TripBooking.objects.filter(otp="").iterator():
        booking.otp = f"{random.randint(0, 9999):04d}"
        booking.save(update_fields=["otp"])


class Migration(migrations.Migration):

    dependencies = [
        ("django_trips", "0010_tripbooking_pickup_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="tripbooking",
            name="otp",
            field=models.CharField(
                default="",
                editable=False,
                max_length=4,
                help_text="Auto-generated 4-digit code, shown once at booking "
                "creation. Paired with `number` as an alternative to `number` "
                "+ `email` for the guest booking lookup endpoint.",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_otp, migrations.RunPython.noop),
    ]

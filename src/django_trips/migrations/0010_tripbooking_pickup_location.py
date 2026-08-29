import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_trips", "0009_reverse_trip_pricing_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="tripbooking",
            name="pickup_location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="Pickup point selected for this booking, if any. Must "
                "be one of the pickup points offered on the booking's own "
                "schedule.",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="django_trips.trippickuplocation",
            ),
        ),
    ]

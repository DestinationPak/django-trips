from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_trips", "0002_bookingstatus_add_ready"),
    ]

    operations = [
        migrations.AddField(
            model_name="tripschedule",
            name="child_price",
            field=models.DecimalField(
                default=0,
                max_digits=7,
                decimal_places=0,
                help_text="Per-child price for this departure. Independent of "
                "`price` rather than a fixed ratio, since child discounts vary "
                "by trip.",
            ),
        ),
        migrations.RenameField(
            model_name="trippickuplocation",
            old_name="trip",
            new_name="schedule",
        ),
    ]

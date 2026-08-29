from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_trips", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tripbooking",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("WAITING_PAYMENT", "Awaiting Payment"),
                    ("CONFIRMED", "Confirmed"),
                    ("READY", "Ready"),
                    ("COMPLETED", "Completed"),
                    ("PARTIAL_PAYMENT", "Partial Payment"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="PENDING",
                help_text="Current status of the booking",
                max_length=20,
            ),
        ),
    ]

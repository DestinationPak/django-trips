"""
Retargets every FK/M2M to Location so its `to=` is the live
settings.DJANGO_TRIPS_LOCATION_MODEL reference, not the literal
'django_trips.location' string these fields were originally migrated
with (P9.2 made Location swappable, but that alone doesn't touch
already-applied migrations - their `to=` value stays frozen at
whatever it was when originally written, regardless of Meta.swappable
being added later). Without this, DJANGO_TRIPS_LOCATION_MODEL has no
effect on the actual database schema: a fresh install would still
create every FK constraint against django_trips_location.

For an installer who never swaps Location, this is a no-op - the
setting still resolves to 'django_trips.location', so nothing in the
schema actually changes.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_trips', '0014_bookingstatusevent'),
        migrations.swappable_dependency(settings.DJANGO_TRIPS_LOCATION_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='testimonial',
            name='location',
            field=models.ForeignKey(blank=True, help_text="Where the person is from, e.g. 'Lahore'.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='testimonials', to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
        migrations.AlterField(
            model_name='trip',
            name='departure',
            field=models.ForeignKey(blank=True, help_text='Starting point of the trip', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='departure_trips', to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
        migrations.AlterField(
            model_name='trip',
            name='destination',
            field=models.ForeignKey(blank=True, help_text='Primary destination of the trip', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='destination_trips', to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
        migrations.AlterField(
            model_name='trip',
            name='locations',
            field=models.ManyToManyField(help_text='All locations visited during the trip', related_name='trips', to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
        migrations.AlterField(
            model_name='tripitinerary',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
        migrations.AlterField(
            model_name='trippickuplocation',
            name='location',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
        migrations.AlterField(
            model_name='tripreview',
            name='location',
            field=models.ForeignKey(blank=True, help_text="Reviewer's home location, e.g. for display as 'Lahore' alongside their review.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='trip_reviews', to=settings.DJANGO_TRIPS_LOCATION_MODEL),
        ),
    ]

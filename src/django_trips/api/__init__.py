"""
DRF API for django-trips, deprecated and removed in 2.0.0.

From 2.0.0 the package ships the domain only: models, querysets and
`django_trips.services`. Build your own API on those instead.
"""

import warnings

warnings.warn(
    "django_trips.api is deprecated and will be removed in django-trips 2.0.0. "
    "Build your own API on django_trips.services and the model querysets.",
    DeprecationWarning,
    stacklevel=2,
)

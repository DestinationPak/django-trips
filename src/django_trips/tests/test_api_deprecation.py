import importlib

from django.test import SimpleTestCase

import django_trips.api


class ApiDeprecationTestCase(SimpleTestCase):
    def test_importing_the_api_warns_it_is_removed_in_2_0(self):
        with self.assertWarnsRegex(DeprecationWarning, "removed in django-trips 2.0.0"):
            importlib.reload(django_trips.api)

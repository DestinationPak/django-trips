"""
Django settings for trips project.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "fake-secret-key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "config_models",
    "crum",
    "django_extensions",
    "django_trips",
    "taggit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "crum.CurrentRequestUserMiddleware",
]

ROOT_URLCONF = "devsite.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "devsite.wsgi.application"

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Database
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DATABASE_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.getenv("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "db"),
        "PORT": os.getenv("DB_PORT", "3306"),
    }
}
# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]




# # # # # # # # # # # # # # # # # # # # # # #
#     Generate trips command args           #
# # # # # # # # # # # # # # # # # # # # # # #
USE_DEFAULT_TRIPS = False

# Maps a region/province name to the location names within it. Used by
# generate_trips to link each seeded Location to a PROVINCE-level parent,
# so generated destinations have a working `region` instead of None.
TRIP_LOCATIONS_BY_REGION = {
    "Gilgit-Baltistan": ("Fairy Meadows", "Hunza", "Gilgit", "Skardu"),
    "Khyber Pakhtunkhwa": ("Swat", "Kaghan"),
    "Azad Kashmir": ("Kashmir",),
    "Punjab": ("Lahore", "Murree"),
    "Sindh": ("Karachi",),
    "Islamabad Capital Territory": ("Islamabad",),
}

TRIP_DESTINATIONS = (
    "Fairy Meadows",
    "Hunza",
    "Gilgit",
    "Kashmir",
    "Murree",
    "Kaghan",
    "Swat",
    "Skardu",
)
TRIP_DEPARTURE_LOCATION = (
    "Lahore",
    "Islamabad",
    "Karachi",
)
TRIP_LOCATIONS = TRIP_DEPARTURE_LOCATION + TRIP_DESTINATIONS

TRIP_HOSTS = ("Arbisoft", "Traverse", "Travel Freaks", "Destivels", "Arbitainment")
TRIP_FACILITIES = (
    "Transport",
    "Meals",
    "Guide",
    "Photography",
    "Accommodation",
    "First Aid Kit",
    "Bon Fire",
    "Power Bank",
)
TRIP_CATEGORIES = (
    "Long Drive",
    "Honeymoon",
    "Road Trip",
    "Bonfire",
    "Hiking",
)
TRIP_GEARS = (
    "Mountain Climber",
    "Shoes",
    "Stick",
    "Coat",
    "Camp",
    "Inhaler",
    "Lighter",
)
TRIP_OPTIONS = ("Deluxe", "Budget", "VIP", "Twin Sharing")


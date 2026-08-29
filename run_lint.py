import sys

import pylint.lint

THRESHOLD = 6

# pylint:disable=all
pylint_opts = [
    "--disable=line-too-long",
    "--load-plugins",
    "pylint_django",
    "--django-settings-module=settings.test",
    "--rcfile=.pylintrc",
    "./src/django_trips",
]

sys.stdout.write(f"Running... {pylint_opts}")

results = pylint.lint.Run(pylint_opts, exit=False)
score = round(results.linter.stats.global_note, 2)

if score < THRESHOLD:
    sys.stdout.write(f"Code quality is below the threshold {score}/{THRESHOLD}.\n")
    sys.exit(1)
sys.exit(0)

"""Test environment for the API unit tests.

`askdocs_api.config` deliberately fails fast when `DATABASE_URL` is missing —
correct at boot, wrong for a unit test that only exercises citation validation
and never opens a connection. Without this, a fresh clone runs `make test` and
gets five `ValidationError: DATABASE_URL Field required` failures that say
nothing about the code under test.

Values are `setdefault`, so a real `.env` or an exported variable still wins.
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://askdocs:askdocs@localhost:5432/askdocs_test"
)
os.environ.setdefault("SESSION_SECRET", "test-only-not-a-secret")

"""Organization slug — a pure function, testable without a database."""

import re

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_MAX_LENGTH = 48


def slugify(value: str) -> str:
    slug = _NON_SLUG.sub("-", value.strip().lower()).strip("-")
    return slug[:_MAX_LENGTH] or "org"

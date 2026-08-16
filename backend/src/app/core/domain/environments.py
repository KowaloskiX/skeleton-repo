"""Application environments. Lives in the domain rather than in config: the type also shows
up in the API contract (`/api/health`), and the domain must not import config."""

from typing import Literal

type AppEnv = Literal["dev", "test", "staging", "prod"]

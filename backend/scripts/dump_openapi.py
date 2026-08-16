"""Dumps the OpenAPI schema to a file — the source for the TS client generator.

The file is committed, so the frontend can generate a client without running the backend, and
CI compares it against the code to catch drift.

Run with: `uv run dump-openapi` (see [project.scripts] in pyproject.toml).
"""

import json
from pathlib import Path

from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict

from app.main import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


class DumpOpenApi(BaseSettings):
    """CLI settings (pydantic-settings instead of argparse — typed and validated)."""

    model_config = SettingsConfigDict(cli_parse_args=True)

    output: Path = DEFAULT_OUTPUT

    def cli_cmd(self) -> None:
        schema = create_app().openapi()
        # sort_keys plus a trailing newline: without them the diff jumps on every dump.
        self.output.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"OpenAPI written to {self.output}")


def main() -> None:
    CliApp.run(DumpOpenApi)


if __name__ == "__main__":
    main()

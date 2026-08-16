"""OpenAPI contract — without it the generated TS client gets ugly, unstable names."""

from fastapi import FastAPI


def test_every_route_has_operation_id_and_exactly_one_tag(app: FastAPI) -> None:
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            where = f"{method.upper()} {path}"
            assert "operationId" in operation, f"{where}: missing operation_id"
            assert len(operation.get("tags", [])) == 1, f"{where}: exactly one tag required"


def test_operation_ids_are_unique_and_kebab_case(app: FastAPI) -> None:
    schema = app.openapi()
    seen: set[str] = set()
    for operations in schema["paths"].values():
        for operation in operations.values():
            operation_id: str = operation["operationId"]
            assert operation_id not in seen, f"duplicate operationId: {operation_id}"
            assert operation_id == operation_id.lower(), operation_id
            assert "_" not in operation_id, f"{operation_id}: use kebab-case"
            seen.add(operation_id)

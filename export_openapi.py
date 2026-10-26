"""Export OpenAPI 3.x schema from the FastAPI application to openapi.json."""

import json
from pathlib import Path
from app.main import app

def export_schema():
    openapi_schema = app.openapi()
    output_path = Path(__file__).parent / "openapi.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"OpenAPI schema successfully exported to {output_path}")

if __name__ == "__main__":
    export_schema()

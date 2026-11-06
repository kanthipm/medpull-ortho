"""Write the API's OpenAPI document to backend/openapi.json, deterministically.

The committed file is the contract the patient apps are generated or checked
against (the Android client's models come from it). `make openapi` refreshes
it; tests/test_api.py fails when it is stale, so a route or schema change
cannot ship without the export moving with it.

    cd backend && uv run python scripts/export_openapi.py          # write
    cd backend && uv run python scripts/export_openapi.py --check  # diff only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND / "openapi.json"


def render() -> str:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.name} is stale: run `make openapi` and commit the result", file=sys.stderr)
            return 1
        print(f"{OUT.name} is current")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

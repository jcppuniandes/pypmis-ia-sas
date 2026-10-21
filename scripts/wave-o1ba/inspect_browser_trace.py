"""Inspect source request auth presence without printing tokens or credentials."""

import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]

for trace in (ROOT / "frontend/test-results").rglob("trace.zip"):
    with ZipFile(trace) as archive:
        matches = []
        for name in archive.namelist():
            if not name.endswith(".network"):
                continue
            for line in archive.read(name).decode("utf-8").splitlines():
                record = json.loads(line)
                snapshot = record.get("snapshot", {})
                request = snapshot.get("request", {})
                if "/scope/" not in request.get("url", "") or not request[
                    "url"
                ].endswith("/source"):
                    continue
                headers = {
                    row["name"].lower(): row["value"]
                    for row in request.get("headers", [])
                }
                matches.append(
                    {
                        "url": request["url"],
                        "status": snapshot.get("response", {}).get("status"),
                        "bearer_present": headers.get("authorization", "").startswith(
                            "Bearer "
                        ),
                        "credential_length": len(headers.get("authorization", "")),
                    }
                )
        print(
            json.dumps(
                {
                    "trace": str(trace.relative_to(ROOT)),
                    "source_requests": matches[-12:],
                }
            )
        )

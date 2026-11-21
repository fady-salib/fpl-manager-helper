"""Local pairing endpoint negative checks. No official account endpoint is called."""

import json
import urllib.error
import urllib.request
from pathlib import Path


def call(path, body, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(
        "http://127.0.0.1:7878" + path, data=json.dumps(body).encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def main():
    assert call("/api/connect/start", {"name": "Fixture XI", "manager": ""})[0] == 400
    assert (
        call(
            "/api/connect/start",
            {"name": "Fixture XI", "manager": "Fixture Manager"},
            "https://evil.test",
        )[0]
        == 403
    )
    code, first = call("/api/connect/start", {"name": "Fixture XI", "manager": "Fixture Manager"})
    assert code == 200 and len(first["token"]) == 64 and first["expires_seconds"] == 300
    assert call("/api/connect/status", {"token": first["token"]})[1]["waiting"]
    assert call("/api/connect/complete", {"token": "bad", "reference": 123})[0] == 403
    assert call("/api/connect/complete", {"token": first["token"], "reference": 0})[0] == 400
    _, second = call("/api/connect/start", {"name": "Other XI", "manager": "Fixture Manager"})
    assert second["token"] != first["token"]
    assert call("/api/connect/status", {"token": first["token"]})[0] == 410
    assert call("/api/connect/status", {"token": second["token"]}, "https://evil.test")[0] == 403
    report = {
        "passed": True,
        "checks": 8,
        "live_account_requests": 0,
        "note": "Names are synthetic; these calls do not complete a real pairing or save a connection registry.",
    }
    Path("reports/connection-api-results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

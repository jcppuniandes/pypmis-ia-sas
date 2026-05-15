from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def assert_contains(path: str, needle: str) -> None:
    content = read(path)
    assert needle in content, f"{path} must contain {needle!r}"


def main() -> None:
    workflow = read(".github/workflows/ci.yml").lower()
    assert "playwright" in workflow, "CI workflow must run Playwright browser E2E"
    assert "test:e2e" in workflow, "CI workflow must call the frontend E2E script"
    assert "alembic current" in workflow, "CI workflow must verify applied migration revision"

    package = json.loads(read("frontend/package.json"))
    assert "test:e2e" in package["scripts"], "frontend package must expose test:e2e"
    assert "@playwright/test" in package["devDependencies"], "frontend must pin @playwright/test"
    assert (ROOT / "frontend/playwright.config.ts").exists(), "Playwright config is required"
    assert (ROOT / "frontend/e2e/production-readiness.spec.ts").exists(), "Production E2E spec is required"

    assert_contains("deploy/vps/deploy.sh", "alembic current")
    assert_contains("deploy/vps/backup.sh", "BACKUP_KEEP")
    assert_contains("deploy/vps/backup.sh", "sha256sum")
    assert (ROOT / "docs/24-operacion-productiva-formal.md").exists(), "Production operations runbook is required"


if __name__ == "__main__":
    main()

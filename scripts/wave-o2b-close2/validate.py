"""Reuse O2B release runners without mixing evidence with the previous cut."""

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2b-close2-20261112"
OLD = ROOT / "scripts/wave-o2b-close"
sys.path.insert(0, str(OLD))
import chromium_gate as chromium
import freeze
import postgres_regression as postgres

HEAD = freeze.HEAD
chromium.SOURCE_PATHS = (
    *chromium.SOURCE_PATHS,
    "frontend/e2e/wave-o2b-close2-consumers.spec.ts",
)


def snapshot():
    base = freeze.snapshot()
    extra = {
        f"scripts/wave-o2b-close2/{name}": chromium.digest(Path(__file__).parent / name)
        for name in ("validate.py", "consumers.py")
    }
    return base | {"sha256": base["sha256"] | extra | chromium.snapshot()}


def browser_consumers(phase, attempt):
    evidence = QA / "chromium/o2b" / attempt
    private = evidence / "private"
    env = chromium.browser_env("o2b", private)
    chromium.assert_prepared(evidence, HEAD, env)
    manifest = private / "consumer-fixture.json"
    if phase == "prepare":
        if manifest.exists():
            raise RuntimeError("Consumer browser fixture already exists")
        env.update(
            PYPMIS_O2B_CLOSE2_BROWSER_FIXTURE="disposable-only",
            PYPMIS_CLOSE2_BROWSER_MANIFEST=str(manifest),
        )
        return chromium.run(
            [sys.executable, "-m", "tests.provision_o2b_close2_consumers"],
            chromium.BACKEND,
            env,
            evidence / "consumer-provision.log",
        )
    junit = evidence / "consumer-junit.xml"
    proof = evidence / "consumer-browser-proof.json"
    env.update(
        E2E_CLOSE2_CONSUMER_FIXTURE=str(manifest),
        E2E_CLOSE2_CONSUMER_OUTPUT=str(evidence),
        PLAYWRIGHT_JUNIT_OUTPUT_FILE=str(junit),
    )
    exit_code = chromium.run(
        [
            "node",
            "node_modules/@playwright/test/cli.js",
            "test",
            "e2e/wave-o2b-close2-consumers.spec.ts",
            "--project=chromium",
            "--workers=1",
            "--reporter=line,junit",
            "--output",
            str(evidence / "consumer-results"),
        ],
        chromium.FRONTEND,
        env,
        evidence / "consumer-playwright.log",
    )
    chromium.assert_prepared(evidence, HEAD, env)
    rows = list(ElementTree.parse(junit).iter("testcase")) if junit.is_file() else []
    report = json.loads(proof.read_text("utf-8")) if proof.is_file() else {}
    expected = json.loads(manifest.read_text("utf-8"))
    passed = (
        not exit_code
        and bool(rows)
        and not any(
            case.find(tag) is not None
            for case in rows
            for tag in ("failure", "error", "skipped")
        )
        and report.get("result") == "PASS"
        and report.get("tenant_id") == expected["tenant_id"]
        and report.get("project_workspace_id") == expected["project_workspace_id"]
    )
    chromium.write(
        evidence / "consumer-browser-source-proof.json",
        {
            "result": "PASS" if passed else "FAIL",
            "alembic_head": HEAD,
            "git_commit": snapshot()["git_commit"],
            "source_sha256": snapshot()["sha256"],
            "junit_cases": len(rows),
            "artifact_sha256": {
                p.name: chromium.digest(p) for p in (junit, proof) if p.is_file()
            },
        },
    )
    return int(not passed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=("freeze", "verify", "pg", "web", "web-consumers", "preservation"),
    )
    parser.add_argument("attempt")
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.attempt):
        parser.error("Invalid attempt")
    gate = QA / "release" / f"freeze-{args.attempt}.json"
    if args.kind == "preservation":
        import preservation

        preservation.observer.OUT = QA / "project-14"
        sys.argv = [sys.argv[0], *args.arguments]
        return preservation.observer.main() or 0
    if args.kind == "freeze":
        gate.parent.mkdir(parents=True, exist_ok=True)
        chromium.write(gate, {"frozen_at_utc": chromium.utc(), "source": snapshot()})
        print(gate)
        return 0
    frozen = json.loads(gate.read_text("utf-8"))
    if frozen["source"] != snapshot():
        raise RuntimeError("Source drift: create a new freeze and rerun evidence")
    if args.kind == "verify":
        print(f"Freeze {args.attempt} verified")
        return 0
    chromium.QA = QA / "chromium"
    if args.kind == "web-consumers":
        return browser_consumers(args.arguments[0], args.attempt)
    module = postgres if args.kind == "pg" else chromium
    if args.kind == "pg":
        postgres.QA = QA / "pg-o1" if args.arguments == ["o1"] else QA / "postgres"
    sys.argv = [sys.argv[0], *args.arguments, args.attempt, "--expected-head", HEAD]
    return module.main()


if __name__ == "__main__":
    sys.exit(main())

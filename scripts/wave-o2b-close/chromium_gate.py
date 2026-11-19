"""Prepare and run isolated G01 browser suites without reusing previous evidence."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
QA = ROOT / "outputs/.qa/wave-o2b-close-20261111/chromium"
WAVES = {
    "o2a": (5554, 8859, 5519, "engineering-foundation.spec.ts"),
    "o2b": (5557, 8860, 5520, "procurement-foundation.spec.ts"),
}
REQUIRED_BROWSER_CHECKS = {
    "o2a": {
        "ADMIN_INDEPENDENT_PUBLISH_IMMUTABLE",
        "REGISTER_AND_REVISION_REAL_UI",
        "CDE_ATTACHMENT_PINNED_BY_REAL_HASH",
        "SCOPE_PLAN_EWP_MAPPINGS_REAL_UI",
        "TWO_ROUNDS_COMMENT_RESPONSE_CLOSE_AND_INDEPENDENT_CHECK_APPROVAL",
        "IFC_EXPLICIT_SEPARATE_ACTOR_AND_RELEASE_HASH",
        "GOVERNED_ENGINEERING_EVIDENCE_CONSUMED_BY_AWP_NO_PACKAGE_RELEASE",
        "APPROVED_REVISION_IMMUTABLE_AND_READS_DO_NOT_MUTATE_HISTORY",
    },
    "o2b": {
        "ADMIN_PROFILE_INDEPENDENT_PUBLICATION",
        "IFC_PINNED_REQUIREMENT_PACKAGE_PWP_DISTINCT",
        "REQUISITION_DISTINCT_APPROVAL",
        "RFQ_TWO_INVITES_INDEPENDENT_ISSUANCE",
        "BIDS_AND_EVALUATIONS_ARE_SEPARATE",
        "AWARD_DOES_NOT_AUTO_CREATE_PO_INDEPENDENT_APPROVAL",
        "PHYSICAL_REQUIREMENT_MILESTONE_INSPECTION_DISTINCT",
        "ARRIVAL_RECEIPT_ACCEPTANCE_ARE_SEPARATE",
        "MATERIAL_READY_CONSUMED_BY_AWP_NO_RELEASE",
        "HISTORY_AND_LOCAL_OBSERVATIONS",
    },
}
SOURCE_PATHS = (
    "backend/alembic",
    "backend/app",
    "backend/tests",
    "backend/alembic.ini",
    "backend/pyproject.toml",
    "backend/requirements.txt",
    "docker-compose.wave-o1c.yml",
    "docker-compose.wave-o2a.yml",
    "docker-compose.wave-o2b.yml",
    "frontend/e2e/engineering-foundation.spec.ts",
    "frontend/e2e/procurement-foundation.spec.ts",
    "frontend/e2e/wave-o2b-close-context.spec.ts",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/playwright.config.ts",
    "frontend/src",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "scripts/wave-o2b-close/chromium_gate.py",
)


def utc():
    return datetime.now(UTC).isoformat()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL
    ).decode("utf-8")


def snapshot():
    paths = set(
        git("ls-files", "-z", "-co", "--exclude-standard", "--", *SOURCE_PATHS).split(
            "\0"
        )
    )
    return {
        path: digest(ROOT / path)
        for path in sorted(paths)
        if path and (ROOT / path).is_file()
    }


def write(path, payload):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)


def run(command, folder, env, log=None):
    if log is None:
        return subprocess.run(command, cwd=folder, env=env, check=False).returncode
    with log.open("xb") as stream:
        return subprocess.run(
            command,
            cwd=folder,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode


def database_head(env):
    code = (
        "from sqlalchemy import create_engine,text; import os; "
        "c=create_engine(os.environ['DATABASE_URL']).connect(); "
        "print(c.execute(text('select version_num from alembic_version')).scalar_one())"
    )
    return subprocess.check_output(
        [sys.executable, "-c", code], cwd=BACKEND, env=env, text=True
    ).strip()


def published_profile(env, tenant_id, profile_id, wave):
    if not isinstance(profile_id, int):
        return None
    code = (
        "from sqlalchemy import create_engine,text; import os,sys,json; "
        "c=create_engine(os.environ['DATABASE_URL']).connect(); "
        "q=c.execute(text('select id, kind, code, revision, version, status, content_hash "
        "from admin_configurations where tenant_id=:tenant and id=:identity and kind=:kind'), "
        "{'tenant':int(sys.argv[1]),'identity':int(sys.argv[2]),'kind':sys.argv[3]}).mappings().one_or_none(); "
        "print(json.dumps(dict(q) if q else None))"
    )
    kind = "engineering_profile" if wave == "o2a" else "procurement_profile"
    return json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code, str(tenant_id), str(profile_id), kind],
            cwd=BACKEND,
            env=env,
            text=True,
        )
    )


def browser_env(wave, private):
    db_port, api_port, front_port, _ = WAVES[wave]
    return {
        **os.environ,
        "DATABASE_URL": f"postgresql+psycopg://{wave}:disposable-{wave}@127.0.0.1:{db_port}/{wave}_browser",
        "AUTO_CREATE_SCHEMA": "false",
        "SEED_DEMO_DATA": "false",
        "RATE_LIMIT_ENABLED": "false",
        "AUTH_SECRET_KEY": f"wave-close-disposable-chromium-fixture-{wave}",
        "DOCUMENT_STORAGE_PATH": str(private / "documents"),
        "ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
        "CORS_ORIGINS": f"http://127.0.0.1:{front_port},http://localhost:{front_port}",
        f"PYPMIS_{wave.upper()}_FIXTURE": "disposable-only",
        f"PYPMIS_{wave.upper()}_ARTIFACT_DIR": str(private),
        "VITE_API_URL": f"http://127.0.0.1:{api_port}",
        "VITE_FRONTEND_VALIDATION_MODE": "false",
        "E2E_API_URL": f"http://127.0.0.1:{api_port}",
        "E2E_BASE_URL": f"http://127.0.0.1:{front_port}",
    }


def prepare(wave, expected, evidence, private, env):
    before = snapshot()
    heads = subprocess.check_output(
        [sys.executable, "-m", "alembic", "heads"], cwd=BACKEND, env=env, text=True
    )
    if re.findall(r"^([^\s]+).*\(head\)", heads, re.MULTILINE) != [expected]:
        raise RuntimeError(
            "Repository Alembic head did not match the declared freeze; nothing migrated"
        )
    evidence.mkdir(parents=True, exist_ok=False)
    private.mkdir(exist_ok=False)
    exit_code = run(
        [sys.executable, "-m", "alembic", "upgrade", expected],
        BACKEND,
        env,
        evidence / "migration.log",
    )
    if exit_code or database_head(env) != expected:
        raise RuntimeError(
            "Isolated migration failed or Alembic head did not match the freeze"
        )
    exit_code = run(
        [sys.executable, "-m", f"tests.provision_{wave}_browser"],
        BACKEND,
        env,
        evidence / "provision.log",
    )
    if exit_code:
        raise RuntimeError("Isolated fixture provisioning failed; see provision.log")
    fixture = json.loads((private / "browser-fixture.json").read_text(encoding="utf-8"))
    if (
        not fixture.get("tenant_id")
        or fixture.get("project_workspace_id") in (None, 0, 14)
        or fixture.get("legacy_project_id") in (None, 0, 14)
    ):
        raise RuntimeError(
            "Fixture identity is missing or matches the protected project"
        )
    if snapshot() != before:
        raise RuntimeError(
            "Source changed during fixture preparation; discard this run's evidence"
        )
    write(
        evidence / "prepared.json",
        {
            "source_sha256": before,
            "git_commit": git("rev-parse", "HEAD").strip(),
            "alembic_head": expected,
            "tenant_id": fixture["tenant_id"],
            "project_workspace_id": fixture["project_workspace_id"],
            "prepared_at_utc": utc(),
        },
    )


def assert_prepared(evidence, expected, env):
    prepared = json.loads((evidence / "prepared.json").read_text(encoding="utf-8"))
    before = snapshot()
    commit = git("rev-parse", "HEAD").strip()
    if prepared["source_sha256"] != before or prepared["git_commit"] != commit:
        raise RuntimeError(
            "Source no longer matches fixture freeze; prepare a new attempt"
        )
    if prepared["alembic_head"] != expected or database_head(env) != expected:
        raise RuntimeError(
            "Isolated database no longer matches the expected Alembic head"
        )
    return prepared, before, commit


def run_chromium(wave, expected, evidence, private, env):
    prepared, before, commit = assert_prepared(evidence, expected, env)
    run_started = evidence / "playwright.log"
    if run_started.exists():
        raise RuntimeError(
            "Existing Chromium attempt cannot be reused; prepare a new synthetic tenant"
        )
    for url in (env["E2E_API_URL"] + "/api/v1/health", env["E2E_BASE_URL"] + "/app"):
        with urlopen(url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Dedicated Chromium service is not ready: {url}")
    started = utc()
    junit_path = evidence / "junit.xml"
    env.update(
        {
            f"E2E_{wave.upper()}_FIXTURE": str(private / "browser-fixture.json"),
            f"E2E_{wave.upper()}_OUTPUT": str(evidence),
            "E2E_O2B_CLOSE_WAVE": wave,
            "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(junit_path),
        }
    )
    spec = WAVES[wave][3]
    exit_code = run(
        [
            "node",
            "node_modules/@playwright/test/cli.js",
            "test",
            f"e2e/{spec}",
            "e2e/wave-o2b-close-context.spec.ts",
            "--project=chromium",
            "--workers=1",
            "--reporter=line,junit",
            "--output",
            str(evidence / "playwright-results"),
        ],
        FRONTEND,
        env,
        run_started,
    )
    after = snapshot()
    report_path = evidence / "browser-uat.json"
    project_context_path = evidence / "project-context.json"
    performance = evidence / "performance.json"
    results = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.is_file()
        else {}
    )
    measurements = (
        json.loads(performance.read_text(encoding="utf-8"))
        if performance.is_file()
        else {}
    )
    project_context = (
        json.loads(project_context_path.read_text(encoding="utf-8"))
        if project_context_path.is_file()
        else {}
    )
    junit = list(ET.parse(junit_path).iter("testcase")) if junit_path.is_file() else []
    passed_junit = len(junit) == 2 and not any(
        testcase.find(item) is not None
        for testcase in junit
        for item in ("failure", "error", "skipped")
    )
    artifacts = {
        path.name: digest(path)
        for path in (
            report_path,
            performance,
            junit_path,
            run_started,
            project_context_path,
        )
        if path.is_file()
    }
    head_matches = database_head(env) == expected
    unchanged = before == after and git("rev-parse", "HEAD").strip() == commit
    observed = {
        check["code"]
        for check in results.get("checks", [])
        if check.get("result") == "PASS"
    }
    missing_checks = sorted(REQUIRED_BROWSER_CHECKS[wave] - observed)
    profile = published_profile(
        env,
        prepared["tenant_id"],
        results.get("observations", {}).get("profile_id"),
        wave,
    )
    profile_verified = bool(
        profile
        and profile["status"] == "published"
        and re.fullmatch(r"[0-9a-f]{64}", profile["content_hash"])
    )
    passed = (
        exit_code == 0
        and unchanged
        and head_matches
        and passed_junit
        and len(artifacts) == 5
        and results.get("result") == "PASS"
        and results.get("project_workspace_id") == prepared["project_workspace_id"]
        and results.get("browser_errors") == []
        and measurements.get("result") == "MEASURED"
        and project_context.get("result") == "PASS"
        and project_context.get("tenant_id") == prepared["tenant_id"]
        and project_context.get("project_workspace_id")
        == prepared["project_workspace_id"]
        and profile_verified
        and not missing_checks
    )
    write(
        evidence / "browser-source-proof.json",
        {
            "result": "PASS" if passed else "FAIL",
            "scope": f"wave-o2b-close/g01/{wave}",
            "git_commit": commit,
            "source_sha256": before,
            "source_unchanged": unchanged,
            "alembic_head": expected,
            "alembic_head_unchanged": head_matches,
            "tenant_id": prepared["tenant_id"],
            "project_workspace_id": prepared["project_workspace_id"],
            "playwright_exit_code": exit_code,
            "junit_passed": passed_junit,
            "missing_critical_checks": missing_checks,
            "published_profile": profile,
            "artifact_sha256": artifacts,
            "started_at_utc": started,
            "finished_at_utc": utc(),
        },
    )
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=("prepare", "build", "serve-api", "serve-frontend", "validate")
    )
    parser.add_argument("wave", choices=WAVES)
    parser.add_argument("attempt", help="Unique directory name, e.g. final-a")
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.attempt):
        parser.error("attempt must be a short lowercase label")
    evidence = QA / args.wave / args.attempt
    private = evidence / "private"
    if subprocess.run(
        ["git", "check-ignore", "-q", "--", str(private / "browser-fixture.json")],
        cwd=ROOT,
        check=False,
    ).returncode:
        raise RuntimeError(
            "Refusing to produce fixture credentials outside Git-ignored QA storage"
        )
    env = browser_env(args.wave, private)
    if args.phase == "prepare":
        prepare(args.wave, args.expected_head, evidence, private, env)
        return 0
    if args.phase == "validate":
        return run_chromium(args.wave, args.expected_head, evidence, private, env)
    assert_prepared(evidence, args.expected_head, env)
    _, api_port, front_port, _ = WAVES[args.wave]
    if args.phase == "serve-api":
        return run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            BACKEND,
            env,
        )
    vite = ["node", "node_modules/vite/bin/vite.js"]
    build = private / "vite-dist"
    if args.phase == "build":
        return run(
            [*vite, "build", "--outDir", str(build)],
            FRONTEND,
            env,
            evidence / "vite-build.log",
        )
    if not (build / "index.html").is_file():
        raise RuntimeError("Build the same attempt before starting Vite preview")
    return run(
        [
            *vite,
            "preview",
            "--outDir",
            str(build),
            "--host",
            "127.0.0.1",
            "--port",
            str(front_port),
            "--strictPort",
        ],
        FRONTEND,
        env,
    )


if __name__ == "__main__":
    sys.exit(main())

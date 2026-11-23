"""Frontend verification against a fixed source cut, preserving prior evidence."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
QA = ROOT / "outputs/.qa/wave-o3b-20261119"
PATHS = [
    "src/features/quality",
    "src/components/AdminConfigurationView.tsx",
    "src/features/workspace-context/WorkspaceOperationalPage.tsx",
    "src/features/awp/AwpWorkspace.tsx",
    "src/features/cost-foundation/CostManagerWorkspace.tsx",
    "src/features/progress-foundation/ProgressManagerWorkspace.tsx",
    "src/features/contracts-foundation/ContractsManagerWorkspace.tsx",
]
TESTS = [
    "src/features/quality/quality.test.tsx",
    "src/features/field-operations/fieldOperations.test.tsx",
    "src/features/progress-foundation/progressFoundation.test.tsx",
    "src/features/awp/awp.test.tsx",
    "src/features/cost-foundation/costFoundation.test.tsx",
    "src/features/contracts-foundation/contractsFoundation.test.tsx",
    "src/features/workspace-context/WorkspaceOperationalPage.test.tsx",
    "src/features/workspace-context/WorkspaceContextProvider.test.tsx",
]


def snapshot():
    return {
        str(path.relative_to(FRONTEND)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (FRONTEND / "src").rglob("*")
        if path.is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--cut", default="frontend-final")
    args = parser.parse_args()
    target = QA / args.cut
    if target.parent != QA:
        raise RuntimeError("Expected one local evidence directory")
    target.mkdir(exist_ok=False)
    before = snapshot()
    commands = [
        ("eslint", ["node_modules/eslint/bin/eslint.js", *PATHS]),
        ("prettier", ["node_modules/prettier/bin/prettier.cjs", "--check", *PATHS]),
        ("typescript", ["node_modules/typescript/bin/tsc", "--noEmit"]),
        (
            "unit",
            [
                "node_modules/vitest/vitest.mjs",
                "run",
                *TESTS,
                "--maxWorkers=1",
                "--minWorkers=1",
                "--reporter=junit",
                f"--outputFile={target / 'unit-junit.xml'}",
            ],
        ),
        (
            "build",
            [
                "node_modules/vite/bin/vite.js",
                "build",
                "--outDir",
                str(target / "dist"),
            ],
        ),
    ]
    results = []
    for name, command in commands:
        with (target / (name + ".log")).open("x", encoding="utf-8") as log:
            result = subprocess.run(
                [args.node, *command],
                cwd=FRONTEND,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        results.append({"check": name, "exit_code": result.returncode})
        print(name, result.returncode, flush=True)
    assert before == snapshot(), "Source changed while validating the frontend cut"
    (target / "result.json").write_text(
        json.dumps(
            {
                "status": "PASS"
                if all(row["exit_code"] == 0 for row in results)
                else "FAIL",
                "checks": results,
                "source_sha256": before,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if any(row["exit_code"] for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

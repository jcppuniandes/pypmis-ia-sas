"""Record the final O3A frontend checks against an unchanged source snapshot."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
QA = ROOT / "outputs/.qa/wave-o3a-20261118"
NODE = Path(
    "C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/node/bin/node.exe"
)
PATHS = [
    "src/features/field-operations",
    "src/components/AdminConfigurationView.tsx",
    "src/features/workspace-context/WorkspaceOperationalPage.tsx",
    "src/features/awp/AwpWorkspace.tsx",
    "src/features/cost-foundation/CostManagerWorkspace.tsx",
    "src/features/progress-foundation/ProgressManagerWorkspace.tsx",
]


def snapshot():
    files = [p for p in (FRONTEND / "src").rglob("*") if p.is_file()]
    return {
        str(p.relative_to(FRONTEND)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }


def main():
    target = QA / "frontend-final"
    target.mkdir(exist_ok=False)
    commands = [
        ("eslint", ["node_modules/eslint/bin/eslint.js", *PATHS]),
        ("prettier", ["node_modules/prettier/bin/prettier.cjs", "--check", *PATHS]),
        ("typescript", ["node_modules/typescript/bin/tsc", "--noEmit"]),
        (
            "unit",
            [
                "node_modules/vitest/vitest.mjs",
                "run",
                "src/features/field-operations/fieldOperations.test.tsx",
                "--reporter=junit",
                f"--outputFile={target / 'junit.xml'}",
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
    before = snapshot()
    results = []
    for name, args in commands:
        started = datetime.now(UTC).isoformat()
        with (target / f"{name}.log").open("x", encoding="utf-8") as log:
            result = subprocess.run(
                [str(NODE), *args],
                cwd=FRONTEND,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        results.append(
            {
                "check": name,
                "exit_code": result.returncode,
                "started_at_utc": started,
                "completed_at_utc": datetime.now(UTC).isoformat(),
                "command": [str(NODE), *args],
            }
        )
        print(f"{name}: exit {result.returncode}", flush=True)
    after = snapshot()
    proof = {
        "passed": before == after and all(r["exit_code"] == 0 for r in results),
        "source_unchanged": before == after,
        "checks": results,
        "source_before": before,
        "source_after": after,
    }
    (target / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    return 0 if proof["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

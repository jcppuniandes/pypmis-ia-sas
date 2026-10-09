from pathlib import Path

import pytest


def test_local_compose_does_not_seed_demo_data_by_default() -> None:
    compose_file = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    if not compose_file.exists():
        pytest.skip("docker-compose.yml is outside the backend container build context")
    compose_text = compose_file.read_text(encoding="utf-8")

    assert 'SEED_DEMO_DATA: "${SEED_DEMO_DATA:-false}"' in compose_text
    assert 'SEED_DEMO_DATA: "true"' not in compose_text

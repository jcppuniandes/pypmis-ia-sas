from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from app.services.ifc_geometry_converter import convert_ifc_geometry


class _FakeElement:
    GlobalId = "GUID-COLUMN-001"
    Name = "Concrete Column"

    def is_a(self) -> str:
        return "IfcColumn"


class _FakeModel:
    def by_id(self, express_id: int) -> _FakeElement:
        assert express_id == 20
        return _FakeElement()


class _FakeIterator:
    def __init__(self) -> None:
        self._used = False

    def initialize(self) -> bool:
        return True

    def get(self) -> SimpleNamespace:
        return SimpleNamespace(
            id=20,
            geometry=SimpleNamespace(
                verts=[0.0, 0.0, 0.0, 1.23456789, 0.0, 0.0, 0.0, 2.0, 0.0],
                faces=[0, 1, 2],
            ),
        )

    def next(self) -> bool:
        if self._used:
            return False
        self._used = True
        return False


class _FakeSettings:
    USE_WORLD_COORDS = "USE_WORLD_COORDS"

    def __init__(self) -> None:
        self.values = {}

    def set(self, key: str, value: object) -> None:
        self.values[key] = value


class _FakeGeom:
    settings = _FakeSettings

    @staticmethod
    def iterator(settings: _FakeSettings, model: _FakeModel, jobs: int) -> _FakeIterator:
        assert jobs == 1
        assert settings.values["USE_WORLD_COORDS"] is True
        assert isinstance(model, _FakeModel)
        return _FakeIterator()


def test_ifc_geometry_converter_writes_backend_cache_artifact(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "model.ifc"
    output_path = tmp_path / "geometry_cache.json"
    source_path.write_text("ISO-10303-21;", encoding="utf-8")
    fake_ifcopenshell = SimpleNamespace(open=lambda path: _FakeModel(), geom=_FakeGeom)
    monkeypatch.setitem(sys.modules, "ifcopenshell", fake_ifcopenshell)

    summary = convert_ifc_geometry(source_path, output_path, jobs=1)

    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary == {"mesh_count": 1, "product_count": 1, "triangle_count": 1}
    assert artifact["engine"] == "ifcopenshell-geometry"
    assert artifact["products"][0]["express_id"] == 20
    assert artifact["products"][0]["global_id"] == "GUID-COLUMN-001"
    assert artifact["products"][0]["ifc_class"] == "IfcColumn"
    assert artifact["products"][0]["name"] == "Concrete Column"
    assert artifact["products"][0]["mesh"]["vertices"] == [0.0, 0.0, 0.0, 1.234568, 0.0, 0.0, 0.0, 2.0, 0.0]
    assert artifact["products"][0]["mesh"]["indices"] == [0, 1, 2]

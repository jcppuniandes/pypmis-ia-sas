"""Safe YAML parser for the canonical tenant configuration."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.modules.enterprise_structure.importer.models import EnterpriseStructureImport
from app.modules.enterprise_structure.importer.normalizer import normalize_configuration


class ConfigurationParseError(ValueError):
    """Raised when an input cannot be parsed into the canonical contract."""


def parse_configuration(path: str | Path) -> EnterpriseStructureImport:
    source = Path(path)
    if source.suffix.lower() not in {".yaml", ".yml"}:
        raise ConfigurationParseError("Nivel 2B accepts canonical .yaml/.yml input; export Excel sheets before use")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigurationParseError(f"Unable to read YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigurationParseError("The YAML root must be an object")
    try:
        parsed = EnterpriseStructureImport.model_validate(payload)
    except ValidationError as exc:
        messages = [f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors()]
        raise ConfigurationParseError("Invalid canonical configuration: " + "; ".join(messages)) from exc
    return normalize_configuration(parsed)

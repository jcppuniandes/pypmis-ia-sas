"""Declarative, non-mutating Enterprise Structure import preview."""

from app.modules.enterprise_structure.importer.parser import parse_configuration
from app.modules.enterprise_structure.importer.validator import build_dry_run

__all__ = ["build_dry_run", "parse_configuration"]

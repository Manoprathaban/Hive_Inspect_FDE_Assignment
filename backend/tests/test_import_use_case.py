"""Unit test proving the application depends on the ``TemplateImporter`` protocol.

The use case receives a mock adapter only; the contract, not the concrete importer, is
what the application layer knows about.
"""

from __future__ import annotations

from app.adapters.importers.mock import MockTemplateImporter
from app.application.use_cases.import_template import ImportTemplateUseCase
from app.domain.models.template import Template
from app.protocols.importers.template_importer import TemplateImporter


def test_mock_importer_satisfies_protocol() -> None:
    assert isinstance(MockTemplateImporter(), TemplateImporter)


def test_import_template_use_case_delegates_to_importer() -> None:
    use_case = ImportTemplateUseCase(importer=MockTemplateImporter())
    result: Template = use_case.execute(b"fake-template-bytes", filename="sample.xml")
    assert result.name == "sample.xml"
    assert result.source == "mock"
    assert result.source_filename == "sample.xml"
    assert result.sections == []
    assert result.issues == []
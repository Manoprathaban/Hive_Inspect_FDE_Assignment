"""Seed the live app with the committed Spectora template.

The assignment requires the deployed app to "open on an imported template", so the
reviewer has something to explore without uploading anything first. This script imports
``sample-data/sheet1.xml`` through the *real* importer and persists it through the *real*
repository, so what lands in the database is exactly what an upload produces: same
hierarchy, same ordering, same import issues.

It deliberately does NOT hand-write SQL. The schema is owned by the migrations, and a
hand-rolled seed would drift from the importer the reviewer is being asked to judge.

Usage
-----
From the repository root::

    uv run python -m scripts.seed_sample_template            # repo root has no pyproject
    cd backend && uv run python -m scripts.seed_sample_template

Options::

    --owner-id UUID   template owner (default: the dev auth user)
    --source PATH     export to import (default: ../sample-data/sheet1.xml)
    --force           import even if the owner already has templates
    --dry-run         parse and report, write nothing

Safety
------
Re-runnable: without ``--force`` it exits 0 when the owner already has templates, so it
is safe to run against the shared dev/deployment database on every deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Allow `python scripts/seed_sample_template.py` as well as `-m scripts.seed_sample_template`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter  # noqa: E402
from app.adapters.repositories.postgres import PostgresTemplateRepository  # noqa: E402
from app.application.use_cases.import_template import ImportTemplateUseCase  # noqa: E402
from app.domain.models.user import AuthProviderKind, UserContext  # noqa: E402

DEFAULT_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_SOURCE = Path(__file__).resolve().parent.parent.parent / "sample-data" / "sheet1.xml"


async def _seed(
    source: Path,
    owner_id: uuid.UUID,
    *,
    force: bool,
    dry_run: bool,
) -> int:
    from app.api.dependencies.providers import get_async_engine

    if not source.is_file():
        print(f"ERROR: source export not found: {source}", file=sys.stderr)
        return 2

    importer = SpectoraXlsxImporter()
    use_case = ImportTemplateUseCase(importer=importer)
    repository = PostgresTemplateRepository(get_async_engine())

    raw = source.read_bytes()
    template = use_case.execute(raw, filename=source.name)

    # Count the domain tree so the log proves the hierarchy survived, not just a row id.
    sections = len(template.sections)
    items = sum(len(section.items) for section in template.sections)
    comments = sum(len(item.comments) for section in template.sections for item in section.items)
    options = sum(
        len(comment.options)
        for section in template.sections
        for item in section.items
        for comment in item.comments
    )

    print(f"Parsed  : {source.name}")
    print(f"Template: {template.name!r}")
    print(
        f"Tree    : {sections} sections / {items} items / {comments} comments / {options} options"
    )
    print(f"Issues  : {len(template.issues)}")

    if dry_run:
        print("DRY RUN: nothing written.")
        return 0

    user = UserContext(user_id=owner_id, provider=AuthProviderKind.DEV)
    existing = await repository.list_for_user(user.user_id)
    if existing and not force:
        print(
            f"SKIP: owner {owner_id} already has {len(existing)} template(s). "
            "Use --force to add another."
        )
        return 0

    saved = await repository.save(template, owner_id=owner_id)
    print(f"SEEDED  : template_id={saved.id}")
    print(f"Owner   : {owner_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="export to import")
    parser.add_argument(
        "--owner-id", type=uuid.UUID, default=DEFAULT_OWNER_ID, help="template owner"
    )
    parser.add_argument("--force", action="store_true", help="import even if templates exist")
    parser.add_argument("--dry-run", action="store_true", help="parse only, write nothing")
    args = parser.parse_args()

    return asyncio.run(_seed(args.source, args.owner_id, force=args.force, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())

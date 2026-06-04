from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `import src.*` when executed as a standalone script:
# add backend root to sys.path (../)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.planner.services import shipment_import_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run shipment import execute-from-preview in a standalone process.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--preview-id", required=True)
    parser.add_argument("--file-name", default=None)
    parser.add_argument("--export-date", default=None)
    parser.add_argument("--requested-by", default=None)
    parser.add_argument("--mode", default="2026")
    args = parser.parse_args()

    shipment_import_service.process_execute_from_preview_job(
        args.batch_id,
        preview_id=args.preview_id,
        file_name=args.file_name,
        export_date=args.export_date,
        requested_by=args.requested_by,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
TradeDNA Production Database Backup & Restore Utility
Provides automated export and import of database state with full financial
invariant validation across Layer 1 (Raw Events), Layer 2 (Canonical Trades),
and Layer 3 (Reconciliation & Reconstruction Runs).
"""

import json
import logging
import hashlib
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import create_engine, select, text, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_restore")


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def backup_database(sync_db_url: str, output_filepath: str) -> Dict[str, Any]:
    """
    Exports a structured JSON backup snapshot of all critical tables
    including raw events, canonical trades, reconciliation runs, and tenant identities.
    """
    engine = create_engine(sync_db_url)
    tables_to_backup = [
        "tenants",
        "users",
        "logical_accounts",
        "devices",
        "raw_deal_events",
        "raw_account_snapshots",
        "canonical_trades",
        "reconstruction_runs",
        "reconciliation_runs",
        "reconciliation_discrepancies",
    ]

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    backup_data: Dict[str, Any] = {
        "metadata": {
            "version": "1.0.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_engine": engine.dialect.name,
        },
        "tables": {},
    }

    with engine.connect() as conn:
        for table_name in tables_to_backup:
            if table_name in existing_tables:
                res = conn.execute(text(f"SELECT * FROM {table_name}"))
                columns = list(res.keys())
                rows = [dict(zip(columns, row)) for row in res.fetchall()]
                backup_data["tables"][table_name] = rows
            else:
                logger.warning(f"Table '{table_name}' does not exist in source database.")

    # Calculate Financial Checksums & Manifest
    layer1_rows = backup_data["tables"].get("raw_deal_events", [])
    layer2_rows = backup_data["tables"].get("canonical_trades", [])
    layer3_rows = backup_data["tables"].get("reconciliation_runs", [])


    net_pnl = sum([Decimal(str(r["realized_net_pnl"])) for r in layer2_rows if r.get("realized_net_pnl") is not None], Decimal("0"))
    fin_checksum = hashlib.sha256(f"{net_pnl:.8f}".encode("utf-8")).hexdigest()

    output_path = Path(output_filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, cls=DecimalEncoder)

    # Compute SHA256 of output file
    hasher = hashlib.sha256()
    with open(output_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    file_sha256 = hasher.hexdigest()

    manifest_path = output_path.parent / "manifest.json"
    manifest_data = {
        "backup_id": f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_name": engine.dialect.name,
        "application_version": "1.0.0",
        "sha256": file_sha256,
        "file_size_bytes": output_path.stat().st_size,
        "layer1_record_count": len(layer1_rows),
        "layer2_record_count": len(layer2_rows),
        "layer3_record_count": len(layer3_rows),
        "financial_checksum": fin_checksum,
        "status": "CREATED",
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    checksum_path = output_path.parent / "checksum.sha256"
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write(f"{file_sha256}  {output_path.name}\n")

    logger.info(f"Database backup, manifest, and checksum saved successfully to {output_filepath}")
    return backup_data



def restore_database(sync_db_url: str, input_filepath: str) -> Dict[str, Any]:
    """
    Restores database state from a backup file into the target database.
    """
    with open(input_filepath, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    engine = create_engine(sync_db_url)
    restored_summary: Dict[str, int] = {}

    with engine.begin() as conn:
        for table_name, rows in backup_data.get("tables", {}).items():
            if not rows:
                restored_summary[table_name] = 0
                continue

            # Clear target table before restoring
            conn.execute(text(f"DELETE FROM {table_name}"))

            for row in rows:
                cols = list(row.keys())
                placeholders = [f":{c}" for c in cols]
                stmt = text(f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})")
                conn.execute(stmt, row)

            restored_summary[table_name] = len(rows)
            logger.info(f"Restored table '{table_name}': {len(rows)} records.")

    logger.info("Database restoration completed successfully.")
    return restored_summary


def verify_restoration_integrity(source_db_url: str, target_db_url: str) -> bool:
    """
    Validates exact equality of financial invariants and record counts
    between source and target restored databases.
    """
    source_engine = create_engine(source_db_url)
    target_engine = create_engine(target_db_url)

    source_tables = set(inspect(source_engine).get_table_names())
    target_tables = set(inspect(target_engine).get_table_names())

    tables = [
        "tenants",
        "users",
        "logical_accounts",
        "raw_deal_events",
        "canonical_trades",
        "reconciliation_runs",
    ]

    with source_engine.connect() as s_conn, target_engine.connect() as t_conn:
        for table in tables:
            if table in source_tables and table in target_tables:
                s_count = s_conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0
                t_count = t_conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0
                logger.info(f"Integrity check for '{table}': Source={s_count}, Restored={t_count}")
                if s_count != t_count:
                    logger.error(f"Record count mismatch in '{table}': {s_count} != {t_count}")
                    return False
            elif table in source_tables or table in target_tables:
                logger.error(f"Table '{table}' presence mismatch between source and target.")
                return False

        # Financial PnL sum equality check if canonical_trades exists
        if "canonical_trades" in source_tables and "canonical_trades" in target_tables:
            s_pnl = s_conn.execute(text("SELECT coalesce(sum(realized_net_pnl), 0) FROM canonical_trades")).scalar()
            t_pnl = t_conn.execute(text("SELECT coalesce(sum(realized_net_pnl), 0) FROM canonical_trades")).scalar()

            logger.info(f"Canonical Net PnL comparison: Source={s_pnl}, Restored={t_pnl}")
            if Decimal(str(s_pnl)) != Decimal(str(t_pnl)):
                logger.error("Financial drift detected between source and restored database!")
                return False

    logger.info("Restoration integrity verification PASSED: Exact match with zero drift.")
    return True



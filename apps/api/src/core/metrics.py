"""
TradeDNA Production Metrics Registry
Thread-safe metrics collection across HTTP, Database, Connector, Ingestion,
Synchronization, Reconstruction, Reconciliation, and Application security.
Zero financial or sensitive credential data is ever collected or exposed.
"""

import time
import threading
from typing import Any, Dict, List


class MetricsRegistry:
    """In-memory thread-safe metrics registry with standard metric primitives."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()

        # HTTP Metrics
        self.requests_total: int = 0
        self.requests_failed_total: int = 0
        self.active_requests: int = 0
        self.request_latencies: List[float] = []

        # Database Metrics
        self.db_connections_active: int = 0
        self.db_connections_idle: int = 0
        self.db_pool_wait_time_ms: float = 0.0
        self.db_query_latencies: List[float] = []
        self.db_connection_errors: int = 0

        # Connector Metrics
        self.connected_devices: int = 0
        self.active_devices: int = 0
        self.stale_devices: int = 0
        self.revoked_devices: int = 0
        self.heartbeat_total: int = 0
        self.heartbeat_failures: int = 0

        # Ingestion Metrics
        self.ingress_events_total: int = 0
        self.ingress_events_rejected: int = 0
        self.duplicate_events_total: int = 0
        self.sequence_gap_events: int = 0
        self.spool_recovery_events: int = 0

        # Synchronization Metrics
        self.sync_started_total: int = 0
        self.sync_completed_total: int = 0
        self.sync_failed_total: int = 0
        self.sync_events_processed: int = 0
        self.sync_durations: List[float] = []

        # Reconstruction Metrics
        self.reconstruction_runs_total: int = 0
        self.reconstruction_failures: int = 0
        self.reconstruction_durations: List[float] = []

        # Reconciliation Metrics
        self.reconciliation_runs_total: int = 0
        self.reconciliation_failures: int = 0
        self.integrity_scores: List[float] = []
        self.integrity_grade_counts: Dict[str, int] = {"AAA": 0, "AA": 0, "A": 0, "B": 0, "C": 0, "F": 0}

        # Application & Security Metrics
        self.authentication_failures: int = 0
        self.rate_limit_hits: int = 0
        self.device_revocations: int = 0
        self.pairing_attempts: int = 0
        self.pairing_failures: int = 0


        # Disaster Recovery & Backup Metrics
        self.backup_started_total: int = 0
        self.backup_completed_total: int = 0
        self.backup_failed_total: int = 0
        self.backup_verified_total: int = 0
        self.backup_corrupted_total: int = 0
        self.restore_started_total: int = 0
        self.restore_completed_total: int = 0
        self.restore_failed_total: int = 0
        self.backup_durations: List[float] = []
        self.restore_durations: List[float] = []
        self.last_backup_size_bytes: int = 0
        self.last_successful_backup_timestamp: Optional[str] = None
        self.last_verified_backup_timestamp: Optional[str] = None

    def record_backup(self, success: bool, verified: bool = False, duration_ms: float = 0.0, size_bytes: int = 0) -> None:
        with self._lock:
            if success:
                self.backup_completed_total += 1
                self.last_successful_backup_timestamp = datetime.now(timezone.utc).isoformat()
                self.last_backup_size_bytes = size_bytes
                if verified:
                    self.backup_verified_total += 1
                    self.last_verified_backup_timestamp = self.last_successful_backup_timestamp
            else:
                self.backup_failed_total += 1
            if duration_ms > 0:
                self.backup_durations.append(duration_ms)

    def record_restore(self, success: bool, duration_ms: float = 0.0) -> None:
        with self._lock:
            if success:
                self.restore_completed_total += 1
            else:
                self.restore_failed_total += 1
            if duration_ms > 0:
                self.restore_durations.append(duration_ms)


    def record_request(self, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self.requests_total += 1
            if status_code >= 400:
                self.requests_failed_total += 1
            self.request_latencies.append(latency_ms)
            if len(self.request_latencies) > 1000:
                self.request_latencies.pop(0)

    def record_heartbeat(self, success: bool = True) -> None:
        with self._lock:
            self.heartbeat_total += 1
            if not success:
                self.heartbeat_failures += 1

    def record_ingress_event(self, accepted: bool = True, is_duplicate: bool = False, is_spool: bool = False) -> None:
        with self._lock:
            self.ingress_events_total += 1
            if not accepted:
                self.ingress_events_rejected += 1
            if is_duplicate:
                self.duplicate_events_total += 1
            if is_spool:
                self.spool_recovery_events += 1

    def record_sync(self, success: bool, duration_ms: float, events_count: int = 0) -> None:
        with self._lock:
            if success:
                self.sync_completed_total += 1
            else:
                self.sync_failed_total += 1
            self.sync_events_processed += events_count
            self.sync_durations.append(duration_ms)
            if len(self.sync_durations) > 500:
                self.sync_durations.pop(0)

    def record_reconciliation(self, score: float, grade: str, success: bool = True) -> None:
        with self._lock:
            self.reconciliation_runs_total += 1
            if not success:
                self.reconciliation_failures += 1
            self.integrity_scores.append(score)
            if len(self.integrity_scores) > 500:
                self.integrity_scores.pop(0)
            if grade in self.integrity_grade_counts:
                self.integrity_grade_counts[grade] += 1

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns structured metrics summary without exposing any sensitive financial or tenant data."""
        with self._lock:
            uptime = time.time() - self._start_time
            avg_req_latency = sum(self.request_latencies) / max(len(self.request_latencies), 1)
            avg_sync_duration = sum(self.sync_durations) / max(len(self.sync_durations), 1)
            avg_integrity_score = sum(self.integrity_scores) / max(len(self.integrity_scores), 1) if self.integrity_scores else 100.0

            return {
                "system": {
                    "uptime_seconds": round(uptime, 2),
                    "active_requests": self.active_requests,
                },
                "http": {
                    "requests_total": self.requests_total,
                    "requests_failed_total": self.requests_failed_total,
                    "avg_latency_ms": round(avg_req_latency, 2),
                },
                "database": {
                    "connections_active": self.db_connections_active,
                    "connections_idle": self.db_connections_idle,
                    "connection_errors": self.db_connection_errors,
                },
                "connector": {
                    "connected_devices": self.connected_devices,
                    "active_devices": self.active_devices,
                    "stale_devices": self.stale_devices,
                    "revoked_devices": self.revoked_devices,
                    "heartbeat_total": self.heartbeat_total,
                    "heartbeat_failures": self.heartbeat_failures,
                },
                "ingestion": {
                    "events_total": self.ingress_events_total,
                    "events_rejected": self.ingress_events_rejected,
                    "duplicate_events_total": self.duplicate_events_total,
                    "sequence_gap_events": self.sequence_gap_events,
                    "spool_recovery_events": self.spool_recovery_events,
                },
                "synchronization": {
                    "sync_started_total": self.sync_started_total,
                    "sync_completed_total": self.sync_completed_total,
                    "sync_failed_total": self.sync_failed_total,
                    "events_processed": self.sync_events_processed,
                    "avg_duration_ms": round(avg_sync_duration, 2),
                },
                "reconstruction": {
                    "runs_total": self.reconstruction_runs_total,
                    "failures_total": self.reconstruction_failures,
                },
                "reconciliation": {
                    "runs_total": self.reconciliation_runs_total,
                    "failures_total": self.reconciliation_failures,
                    "avg_integrity_score": round(avg_integrity_score, 2),
                    "grade_distribution": dict(self.integrity_grade_counts),
                },
                "security": {
                    "authentication_failures": self.authentication_failures,
                    "rate_limit_hits": self.rate_limit_hits,
                    "device_revocations": self.device_revocations,
                    "pairing_attempts": self.pairing_attempts,
                    "pairing_failures": self.pairing_failures,
                },
                "disaster_recovery": {
                    "backup_completed_total": self.backup_completed_total,
                    "backup_failed_total": self.backup_failed_total,
                    "backup_verified_total": self.backup_verified_total,
                    "restore_completed_total": self.restore_completed_total,
                    "restore_failed_total": self.restore_failed_total,
                    "last_successful_backup_at": self.last_successful_backup_timestamp,
                    "last_verified_backup_at": self.last_verified_backup_timestamp,
                    "last_backup_size_bytes": self.last_backup_size_bytes,
                },
            }


metrics = MetricsRegistry()

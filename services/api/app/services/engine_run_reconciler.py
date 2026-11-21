"""Cooperative stop reconciler for external engine processes.

هذا العامل لا ينفذ مهام المستخدم؛ يستعيد سجلات stop_pending ويطلب إيقاف
المحرك الخارجي ثم يغلق سجل SULY فقط بعد تأكيد حالة نهائية.
"""
from __future__ import annotations

from collections.abc import Callable
import logging

from app.services.engine_run_store import EngineRunStore, EngineStopClaim


logger = logging.getLogger(__name__)

StopHandler = Callable[[str], bool]
ClaimStopHandler = Callable[[EngineStopClaim], bool]


class EngineRunReconciler:
    """Process bounded, lease-claimed stop requests for supported engines."""

    def __init__(
        self,
        store: EngineRunStore,
        *,
        stop_handlers: dict[str, StopHandler] | None = None,
        claim_handlers: dict[str, ClaimStopHandler] | None = None,
        batch_size: int = 10,
        lease_seconds: int = 60,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 100:
            raise ValueError("invalid_engine_stop_claim_bounds")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 15 <= lease_seconds <= 900:
            raise ValueError("invalid_engine_stop_claim_bounds")
        self._store = store
        self._stop_handlers = dict(stop_handlers or {})
        self._claim_handlers = dict(claim_handlers or {})
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._last_missing_identity_count = 0

    def run_once(self) -> int:
        """Return the number of external stops confirmed in this bounded batch."""
        # راقب نافذة الانقطاع النادرة بين إنشاء التشغيل الخارجي وحفظ معرفه في SULY.
        missing_identity_count = self._store.count_missing_upstream_identity(30)
        if missing_identity_count and missing_identity_count != self._last_missing_identity_count:
            logger.error(
                "External engine runs are stop_pending without an upstream identity: %s",
                missing_identity_count,
            )
        self._last_missing_identity_count = missing_identity_count
        # أولاً نحول أي run انتهى lease مالكه إلى stop_pending، ثم نحجزه للإيقاف.
        self._store.reconcile_orphans(self._batch_size)
        claims = self._store.claim_pending_stops(
            self._batch_size,
            self._lease_seconds,
        )
        confirmed_count = 0
        for claim in claims:
            claim_handler = self._claim_handlers.get(claim.engine_id)
            handler = self._stop_handlers.get(claim.engine_id)
            confirmed = False
            try:
                if claim_handler is not None:
                    confirmed = claim_handler(claim) is True
                elif handler is not None and claim.upstream_run_id is not None:
                    confirmed = handler(claim.upstream_run_id) is True
            except Exception:
                # لا نسجل exception text؛ قد يحتوي على بيانات من المحرك الخارجي.
                confirmed = False
            finalized = self._store.finish_stop_reconciliation(
                claim,
                stop_confirmed=confirmed,
            )
            if confirmed and finalized is True:
                confirmed_count += 1
        return confirmed_count

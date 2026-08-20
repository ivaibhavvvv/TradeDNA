"""TradeDNA Phase 5 - Instrument Specification & FX Conversion Service
Resolves contract sizes, tick values, calculation modes, and historical FX rates.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ValidationException
from src.models.instrument_spec import HistoricalExchangeRate, InstrumentSpecification


class MissingInstrumentSpecificationException(ValidationException):
    """Raised when an instrument specification cannot be resolved."""
    pass


class MissingExchangeRateException(ValidationException):
    """Raised when a required historical FX rate is unavailable."""
    pass


# Standard financial market default specifications
DEFAULT_SPECS = {
    "EURUSD": {"contract_size": Decimal("100000"), "tick_size": Decimal("0.00001"), "tick_value": Decimal("1.0"), "digits": 5, "base": "EUR", "quote": "USD", "profit": "USD", "mode": "FOREX"},
    "GBPUSD": {"contract_size": Decimal("100000"), "tick_size": Decimal("0.00001"), "tick_value": Decimal("1.0"), "digits": 5, "base": "GBP", "quote": "USD", "profit": "USD", "mode": "FOREX"},
    "USDJPY": {"contract_size": Decimal("100000"), "tick_size": Decimal("0.001"), "tick_value": Decimal("1.0"), "digits": 3, "base": "USD", "quote": "JPY", "profit": "JPY", "mode": "FOREX"},
    "EURGBP": {"contract_size": Decimal("100000"), "tick_size": Decimal("0.00001"), "tick_value": Decimal("1.0"), "digits": 5, "base": "EUR", "quote": "GBP", "profit": "GBP", "mode": "FOREX"},
    "XAUUSD": {"contract_size": Decimal("100"), "tick_size": Decimal("0.01"), "tick_value": Decimal("1.0"), "digits": 2, "base": "XAU", "quote": "USD", "profit": "USD", "mode": "CFD"},
    "BTCUSD": {"contract_size": Decimal("1"), "tick_size": Decimal("0.01"), "tick_value": Decimal("0.01"), "digits": 2, "base": "BTC", "quote": "USD", "profit": "USD", "mode": "CRYPTO"},
    "US30": {"contract_size": Decimal("1"), "tick_size": Decimal("1.0"), "tick_value": Decimal("1.0"), "digits": 1, "base": "USD", "quote": "USD", "profit": "USD", "mode": "CFD"},
}


class InstrumentService:
    """Service for managing instrument specifications and historical FX conversion rates."""

    @classmethod
    async def get_or_create_default_spec(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        symbol: str,
        effective_time: Optional[datetime] = None,
    ) -> InstrumentSpecification:
        """Resolves existing instrument specification or seeds a default specification."""
        clean_sym = symbol.upper().strip()
        now_utc = effective_time or datetime.now(timezone.utc)

        stmt = select(InstrumentSpecification).where(
            InstrumentSpecification.tenant_id == tenant_id,
            InstrumentSpecification.symbol == clean_sym,
            InstrumentSpecification.effective_from_utc <= now_utc,
            or_(
                InstrumentSpecification.effective_to_utc.is_(None),
                InstrumentSpecification.effective_to_utc > now_utc,
            ),
        ).order_by(InstrumentSpecification.effective_from_utc.desc())

        res = await session.execute(stmt)
        spec = res.scalars().first()
        if spec:
            return spec

        # Fallback to seed defaults
        defaults = DEFAULT_SPECS.get(clean_sym, {
            "contract_size": Decimal("100000"),
            "tick_size": Decimal("0.00001"),
            "tick_value": Decimal("1.0"),
            "digits": 5,
            "base": clean_sym[:3] if len(clean_sym) >= 6 else "USD",
            "quote": clean_sym[3:6] if len(clean_sym) >= 6 else "USD",
            "profit": clean_sym[3:6] if len(clean_sym) >= 6 else "USD",
            "mode": "FOREX",
        })

        new_spec = InstrumentSpecification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            symbol=clean_sym,
            contract_size=defaults["contract_size"],
            tick_size=defaults["tick_size"],
            tick_value=defaults["tick_value"],
            digits=defaults["digits"],
            base_currency=defaults["base"],
            quote_currency=defaults["quote"],
            profit_currency=defaults["profit"],
            calculation_mode=defaults["mode"],
            effective_from_utc=datetime(2020, 1, 1, tzinfo=timezone.utc),
            effective_to_utc=None,
        )
        try:
            async with session.begin_nested():
                session.add(new_spec)
                await session.flush()
            return new_spec
        except Exception:
            # Another concurrent transaction might have created it
            res_retry = await session.execute(stmt)
            spec_retry = res_retry.scalars().first()
            if spec_retry:
                return spec_retry
            return new_spec

    @classmethod
    async def resolve_specification(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        symbol: str,
        effective_time: datetime,
    ) -> InstrumentSpecification:
        """Strictly resolves specification; raises exception if not found."""
        clean_sym = symbol.upper().strip()
        stmt = select(InstrumentSpecification).where(
            InstrumentSpecification.tenant_id == tenant_id,
            InstrumentSpecification.symbol == clean_sym,
            InstrumentSpecification.effective_from_utc <= effective_time,
            or_(
                InstrumentSpecification.effective_to_utc.is_(None),
                InstrumentSpecification.effective_to_utc > effective_time,
            ),
        ).order_by(InstrumentSpecification.effective_from_utc.desc())

        res = await session.execute(stmt)
        spec = res.scalars().first()
        if not spec:
            raise MissingInstrumentSpecificationException(
                f"No instrument specification found for symbol '{clean_sym}' at timestamp {effective_time.isoformat()}"
            )
        return spec

    @classmethod
    async def resolve_fx_rate(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        from_currency: str,
        to_currency: str,
        timestamp_msc: int,
    ) -> Decimal:
        """Resolves historical exchange rate for multi-currency settlement."""
        from_c = from_currency.upper().strip()
        to_c = to_currency.upper().strip()

        if from_c == to_c:
            return Decimal("1.000000")

        # Query direct rate (from_c -> to_c)
        stmt_direct = select(HistoricalExchangeRate).where(
            HistoricalExchangeRate.tenant_id == tenant_id,
            HistoricalExchangeRate.base_currency == from_c,
            HistoricalExchangeRate.quote_currency == to_c,
            HistoricalExchangeRate.effective_time_msc <= timestamp_msc,
        ).order_by(HistoricalExchangeRate.effective_time_msc.desc())

        res_direct = await session.execute(stmt_direct)
        direct = res_direct.scalars().first()
        if direct:
            return direct.rate

        # Query inverse rate (to_c -> from_c)
        stmt_inv = select(HistoricalExchangeRate).where(
            HistoricalExchangeRate.tenant_id == tenant_id,
            HistoricalExchangeRate.base_currency == to_c,
            HistoricalExchangeRate.quote_currency == from_c,
            HistoricalExchangeRate.effective_time_msc <= timestamp_msc,
        ).order_by(HistoricalExchangeRate.effective_time_msc.desc())

        res_inv = await session.execute(stmt_inv)
        inv = res_inv.scalars().first()
        if inv and inv.rate > 0:
            return Decimal("1.0") / inv.rate

        raise MissingExchangeRateException(
            f"No historical exchange rate available between {from_c} and {to_c} at timestamp {timestamp_msc}"
        )

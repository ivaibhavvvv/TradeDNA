"""TradeDNA Phase 8D-A - Golden Exness Dataset Generator.
Provides mathematically authoritative multi-instrument synthetic and real Exness execution histories
across 14 instruments and 10 complex execution scenarios with exact Decimal precision.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List
import uuid


def generate_golden_exness_dataset(
    tenant_id: uuid.UUID,
    account_number: int = 888001,
    server_name: str = "Exness-Real1",
    base_time: datetime | None = None,
) -> Dict[str, Any]:
    """Generates a complete Golden Exness test dataset covering:
    14 Instruments: EURUSD, GBPUSD, USDJPY, USDCAD, EURGBP, GBPJPY, AUDNZD, XAUUSD, XAGUSD, USOIL, US30, USTEC, BTCUSD, ETHUSD.
    10 Scenarios: Clean roundtrip, Partial close, Scale-in, Hedging, Triple swap, Zero-spread raw,
                  Variable spread pro, Stop-out, Slippage, and Deposit/Withdrawal balance events.
    """
    if base_time is None:
        base_time = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 1. Non-Trading Financial Events (Deposits & Withdrawals)
    balance_events = [
        {
            "event_type": "DEPOSIT",
            "amount": Decimal("10000.00"),
            "timestamp": base_time,
            "comment": "Initial Wire Deposit",
            "is_trading_pnl": False,
        },
        {
            "event_type": "WITHDRAWAL",
            "amount": Decimal("-1000.00"),
            "timestamp": base_time + timedelta(days=15),
            "comment": "Client Profit Withdrawal",
            "is_trading_pnl": False,
        },
    ]

    # 2. Multi-Instrument Scenarios List
    # Format: dict with scenario_name, symbol, trades/deals, expected_gross, expected_commission, expected_swap, expected_net
    scenarios: List[Dict[str, Any]] = [
        # Scenario 1: Clean Single Roundtrip (EURUSD, Major)
        {
            "name": "1. Clean Single Roundtrip",
            "symbol": "EURUSD",
            "side": "BUY",
            "position_ticket": 100101,
            "entry_deal": {
                "ticket": 200101,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.08500"),
                "time": base_time + timedelta(hours=1),
                "commission": Decimal("-3.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 200102,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.08800"),  # +30 pips = $300 on 1.00 lot
                "time": base_time + timedelta(hours=2),
                "commission": Decimal("-3.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("300.00"),
            },
            "expected_gross_pnl": Decimal("300.00"),
            "expected_commission": Decimal("-7.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("293.00"),
        },

        # Scenario 2: Partial Close Sequence (XAUUSD, Commodity Gold)
        {
            "name": "2. Partial Close Sequence",
            "symbol": "XAUUSD",
            "side": "BUY",
            "position_ticket": 100201,
            "contract_size": Decimal("100.00"),  # 100 oz per lot for Gold
            "entry_deal": {
                "ticket": 200201,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("2400.00"),
                "time": base_time + timedelta(hours=3),
                "commission": Decimal("-5.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "partial_exits": [
                {
                    "ticket": 200202,
                    "entry_type": "OUT",
                    "volume": Decimal("0.3000"),
                    "price": Decimal("2410.00"),  # +$10/oz * 30oz = +$300
                    "time": base_time + timedelta(hours=4),
                    "commission": Decimal("-1.50"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("300.00"),
                },
                {
                    "ticket": 200203,
                    "entry_type": "OUT",
                    "volume": Decimal("0.3000"),
                    "price": Decimal("2420.00"),  # +$20/oz * 30oz = +$600
                    "time": base_time + timedelta(hours=5),
                    "commission": Decimal("-1.50"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("600.00"),
                },
                {
                    "ticket": 200204,
                    "entry_type": "OUT",
                    "volume": Decimal("0.4000"),
                    "price": Decimal("2430.00"),  # +$30/oz * 40oz = +$1200
                    "time": base_time + timedelta(hours=6),
                    "commission": Decimal("-2.00"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("1200.00"),
                },
            ],
            "expected_gross_pnl": Decimal("2100.00"),
            "expected_commission": Decimal("-10.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("2090.00"),
        },

        # Scenario 3: Scale-In / Pyramiding (GBPUSD, Major)
        {
            "name": "3. Scale-In Pyramiding",
            "symbol": "GBPUSD",
            "side": "BUY",
            "position_ticket": 100301,
            "entry_deals": [
                {
                    "ticket": 200301,
                    "entry_type": "IN",
                    "volume": Decimal("0.5000"),
                    "price": Decimal("1.28000"),
                    "time": base_time + timedelta(hours=7),
                    "commission": Decimal("-1.75"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                },
                {
                    "ticket": 200302,
                    "entry_type": "IN",
                    "volume": Decimal("0.5000"),
                    "price": Decimal("1.28400"),  # VWAP Entry = 1.28200
                    "time": base_time + timedelta(hours=8),
                    "commission": Decimal("-1.75"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                },
            ],
            "exit_deal": {
                "ticket": 200303,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.29000"),  # +80 pips above VWAP = +$800
                "time": base_time + timedelta(hours=9),
                "commission": Decimal("-3.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("800.00"),
            },
            "expected_vwap_entry": Decimal("1.28200"),
            "expected_gross_pnl": Decimal("800.00"),
            "expected_commission": Decimal("-7.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("793.00"),
        },

        # Scenario 4: Hedging Simultaneous Opposing Positions (USDJPY, JPY Scaling)
        {
            "name": "4. Hedging Opposing Positions",
            "symbol": "USDJPY",
            "long_position": {
                "ticket": 100401,
                "side": "BUY",
                "entry_deal": {
                    "ticket": 200401,
                    "entry_type": "IN",
                    "volume": Decimal("1.0000"),
                    "price": Decimal("155.000"),
                    "time": base_time + timedelta(hours=10),
                    "commission": Decimal("-3.00"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                },
                "exit_deal": {
                    "ticket": 200402,
                    "entry_type": "OUT",
                    "volume": Decimal("1.0000"),
                    "price": Decimal("156.000"),  # +100 pips
                    "time": base_time + timedelta(hours=12),
                    "commission": Decimal("-3.00"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("641.03"),
                },
                "expected_net_pnl": Decimal("635.03"),
            },
            "short_position": {
                "ticket": 100402,
                "side": "SELL",
                "entry_deal": {
                    "ticket": 200403,
                    "entry_type": "IN",
                    "volume": Decimal("1.0000"),
                    "price": Decimal("155.000"),
                    "time": base_time + timedelta(hours=10, minutes=5),
                    "commission": Decimal("-3.00"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("0.00"),
                },
                "exit_deal": {
                    "ticket": 200404,
                    "entry_type": "OUT",
                    "volume": Decimal("1.0000"),
                    "price": Decimal("156.000"),  # -100 pips loss
                    "time": base_time + timedelta(hours=12, minutes=5),
                    "commission": Decimal("-3.00"),
                    "swap": Decimal("0.00"),
                    "profit": Decimal("-641.03"),
                },
                "expected_net_pnl": Decimal("-647.03"),
            },
        },

        # Scenario 5: Triple-Swap Wednesday Rollover (GBPJPY, Cross JPY)
        {
            "name": "5. Triple-Swap Wednesday Rollover",
            "symbol": "GBPJPY",
            "side": "BUY",
            "position_ticket": 100501,
            "entry_deal": {
                "ticket": 200501,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("198.500"),
                "time": datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc),  # Wednesday afternoon
                "commission": Decimal("-3.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 200502,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("198.500"),  # Breakeven price
                "time": datetime(2026, 8, 6, 9, 0, 0, tzinfo=timezone.utc),  # Thursday morning (held overnight across 00:00 UTC)
                "commission": Decimal("-3.50"),
                "swap": Decimal("-36.45"),  # 3x standard daily swap of -12.15
                "profit": Decimal("0.00"),
            },
            "expected_gross_pnl": Decimal("0.00"),
            "expected_commission": Decimal("-7.00"),
            "expected_swap": Decimal("-36.45"),
            "expected_net_pnl": Decimal("-43.45"),
        },

        # Scenario 6: Zero-Spread Raw Account with Fixed Commission (EURGBP, Cross)
        {
            "name": "6. Zero-Spread Raw Account",
            "symbol": "EURGBP",
            "side": "SELL",
            "position_ticket": 100601,
            "entry_deal": {
                "ticket": 200601,
                "entry_type": "IN",
                "volume": Decimal("2.0000"),
                "price": Decimal("0.85500"),
                "time": base_time + timedelta(days=2, hours=1),
                "commission": Decimal("-7.00"),  # $3.50/lot each way
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 200602,
                "entry_type": "OUT",
                "volume": Decimal("2.0000"),
                "price": Decimal("0.85300"),  # +20 pips = +£400 = +$520
                "time": base_time + timedelta(days=2, hours=3),
                "commission": Decimal("-7.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("520.00"),
            },
            "expected_gross_pnl": Decimal("520.00"),
            "expected_commission": Decimal("-14.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("506.00"),
        },

        # Scenario 7: Variable Spread Pro Account (AUDNZD, Forex Cross)
        {
            "name": "7. Variable Spread Pro Account",
            "symbol": "AUDNZD",
            "side": "BUY",
            "position_ticket": 100701,
            "entry_deal": {
                "ticket": 200701,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.09250"),
                "time": base_time + timedelta(days=3, hours=4),
                "commission": Decimal("0.00"),  # Zero commission on Pro account
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 200702,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.09650"),  # +40 pips = +$245.00
                "time": base_time + timedelta(days=3, hours=8),
                "commission": Decimal("0.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("245.00"),
            },
            "expected_gross_pnl": Decimal("245.00"),
            "expected_commission": Decimal("0.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("245.00"),
        },

        # Scenario 8: Stop-Out / Forced Margin Liquidation (BTCUSD, Crypto)
        {
            "name": "8. Forced Margin Stop-Out",
            "symbol": "BTCUSD",
            "side": "BUY",
            "position_ticket": 100801,
            "entry_deal": {
                "ticket": 200801,
                "entry_type": "IN",
                "volume": Decimal("0.1000"),
                "price": Decimal("65000.00"),
                "time": base_time + timedelta(days=4, hours=2),
                "commission": Decimal("-6.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 200802,
                "entry_type": "OUT",
                "volume": Decimal("0.1000"),
                "price": Decimal("58000.00"),  # -$7000/coin * 0.10 = -$700 loss
                "time": base_time + timedelta(days=4, hours=6),
                "commission": Decimal("-6.50"),
                "swap": Decimal("-1.20"),
                "profit": Decimal("-700.00"),
                "comment": "so: 0.0%/0.0/0.0",  # MT5 stop-out comment string
            },
            "expected_gross_pnl": Decimal("-700.00"),
            "expected_commission": Decimal("-13.00"),
            "expected_swap": Decimal("-1.20"),
            "expected_net_pnl": Decimal("-714.20"),
        },

        # Scenario 9: Instant vs Market Slippage (US30 & USTEC, Indices)
        {
            "name": "9. Index Execution Slippage",
            "symbol": "US30",
            "side": "SELL",
            "position_ticket": 100901,
            "entry_deal": {
                "ticket": 200901,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("40105.50"),  # Order placed at 40100.00 (+5.5 pts slippage)
                "time": base_time + timedelta(days=5, hours=14, minutes=30),
                "commission": Decimal("-2.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 200902,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("39950.00"),  # +155.5 pts gain = +$155.50
                "time": base_time + timedelta(days=5, hours=15, minutes=0),
                "commission": Decimal("-2.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("155.50"),
            },
            "expected_gross_pnl": Decimal("155.50"),
            "expected_commission": Decimal("-4.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("151.50"),
        },

        # Scenario 10: Commodity Crude Oil (USOIL)
        {
            "name": "10. Commodity Crude Oil",
            "symbol": "USOIL",
            "side": "BUY",
            "position_ticket": 101001,
            "contract_size": Decimal("1000.00"),  # 1,000 barrels per lot
            "entry_deal": {
                "ticket": 201001,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("78.25"),
                "time": base_time + timedelta(days=6, hours=8),
                "commission": Decimal("-3.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 201002,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("79.75"),  # +$1.50/barrel * 1000bbl = +$1500.00
                "time": base_time + timedelta(days=6, hours=16),
                "commission": Decimal("-3.00"),
                "swap": Decimal("-4.80"),
                "profit": Decimal("1500.00"),
            },
            "expected_gross_pnl": Decimal("1500.00"),
            "expected_commission": Decimal("-6.00"),
            "expected_swap": Decimal("-4.80"),
            "expected_net_pnl": Decimal("1489.20"),
        },

        # Scenario 10b: High-Precision Ethereum Slicing (ETHUSD)
        {
            "name": "10b. High-Precision Ethereum Slicing",
            "symbol": "ETHUSD",
            "side": "SELL",
            "position_ticket": 101002,
            "entry_deal": {
                "ticket": 201003,
                "entry_type": "IN",
                "volume": Decimal("0.5000"),
                "price": Decimal("3250.00"),
                "time": base_time + timedelta(days=7, hours=2),
                "commission": Decimal("-3.25"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 201004,
                "entry_type": "OUT",
                "volume": Decimal("0.5000"),
                "price": Decimal("3200.00"),  # +$50 * 0.50 = +$25.00
                "time": base_time + timedelta(days=7, hours=6),
                "commission": Decimal("-3.25"),
                "swap": Decimal("0.00"),
                "profit": Decimal("25.00"),
            },
            "expected_gross_pnl": Decimal("25.00"),
            "expected_commission": Decimal("-6.50"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("18.50"),
        },

        # Scenario 10c: Nasdaq High-Growth Index (USTEC)
        {
            "name": "10c. Nasdaq High-Growth Index",
            "symbol": "USTEC",
            "side": "BUY",
            "position_ticket": 101003,
            "entry_deal": {
                "ticket": 201005,
                "entry_type": "IN",
                "volume": Decimal("0.2000"),
                "price": Decimal("19500.00"),
                "time": base_time + timedelta(days=8, hours=15),
                "commission": Decimal("-1.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 201006,
                "entry_type": "OUT",
                "volume": Decimal("0.2000"),
                "price": Decimal("19600.00"),  # +100 pts * 0.20 = +$20.00
                "time": base_time + timedelta(days=8, hours=16),
                "commission": Decimal("-1.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("20.00"),
            },
            "expected_gross_pnl": Decimal("20.00"),
            "expected_commission": Decimal("-3.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("17.00"),
        },

        # Scenario 10d: USDCAD Major FX with CAD Quote Currency (NEW)
        {
            "name": "10d. USDCAD Major FX (CAD Quote Currency)",
            "symbol": "USDCAD",
            "side": "BUY",
            "position_ticket": 101004,
            "contract_size": Decimal("100000.00"),  # 100,000 USD contract size
            "price_precision": 5,
            "tick_size": Decimal("0.00001"),
            "entry_deal": {
                "ticket": 201007,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.36000"),
                "time": base_time + timedelta(days=9, hours=10),
                "commission": Decimal("-3.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 201008,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("1.36500"),  # +50 pips = +500.00 CAD = +$366.30 USD (at 1.36500 rate)
                "time": base_time + timedelta(days=9, hours=14),
                "commission": Decimal("-3.50"),
                "swap": Decimal("0.00"),
                "profit": Decimal("366.30"),
            },
            "expected_gross_pnl": Decimal("366.30"),
            "expected_commission": Decimal("-7.00"),
            "expected_swap": Decimal("0.00"),
            "expected_net_pnl": Decimal("359.30"),
        },

        # Scenario 10e: XAGUSD Silver Commodity Metal (NEW)
        {
            "name": "10e. XAGUSD Silver Commodity Metal",
            "symbol": "XAGUSD",
            "side": "SELL",
            "position_ticket": 101005,
            "contract_size": Decimal("5000.00"),  # 5,000 troy oz per lot (distinct from Gold 100 oz)
            "price_precision": 3,
            "tick_size": Decimal("0.001"),
            "entry_deal": {
                "ticket": 201009,
                "entry_type": "IN",
                "volume": Decimal("1.0000"),
                "price": Decimal("29.500"),
                "time": base_time + timedelta(days=10, hours=8),
                "commission": Decimal("-5.00"),
                "swap": Decimal("0.00"),
                "profit": Decimal("0.00"),
            },
            "exit_deal": {
                "ticket": 201010,
                "entry_type": "OUT",
                "volume": Decimal("1.0000"),
                "price": Decimal("29.000"),  # +$0.500/oz * 5,000 oz = +$2,500.00 gross gain
                "time": base_time + timedelta(days=10, hours=18),
                "commission": Decimal("-5.00"),
                "swap": Decimal("-5.20"),
                "profit": Decimal("2500.00"),
            },
            "expected_gross_pnl": Decimal("2500.00"),
            "expected_commission": Decimal("-10.00"),
            "expected_swap": Decimal("-5.20"),
            "expected_net_pnl": Decimal("2484.80"),
        },
    ]

    return {
        "tenant_id": tenant_id,
        "account_number": account_number,
        "server_name": server_name,
        "currency": "USD",
        "balance_events": balance_events,
        "scenarios": scenarios,
    }

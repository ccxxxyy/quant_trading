"""数据存储的单元测试。"""

import tempfile
from datetime import datetime
from decimal import Decimal

from quant_trading.data.store import DataStore
from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval

IID = InstrumentId("TEST", Exchange.SSE)


def make_bars(n: int = 5) -> list[Bar]:
    bars = []
    for i in range(n):
        bars.append(
            Bar(
                instrument_id=IID,
                timestamp=datetime(2023, 6, i + 1),
                interval=BarInterval.DAILY,
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("95"),
                close=Decimal("102"),
                volume=10000,
            )
        )
    return bars


class TestDataStore:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DataStore(base_dir=tmpdir)
            bars = make_bars(5)
            count = store.save_bars(IID, bars)
            assert count == 5

            loaded = store.load_bars(IID, BarInterval.DAILY)
            assert len(loaded) == 5
            assert loaded[0].close == Decimal("102")

    def test_list_instruments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DataStore(base_dir=tmpdir)
            bars = make_bars(3)
            store.save_bars(IID, bars)

            instruments = store.list_instruments()
            assert "TEST.SSE" in instruments

    def test_load_with_date_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DataStore(base_dir=tmpdir)
            bars = make_bars(5)
            store.save_bars(IID, bars)

            loaded = store.load_bars(
                IID,
                BarInterval.DAILY,
                start=datetime(2023, 6, 2),
                end=datetime(2023, 6, 4),
            )
            assert len(loaded) == 3  # 6/2, 6/3, 6/4

    def test_save_empty_bars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DataStore(base_dir=tmpdir)
            count = store.save_bars(IID, [])
            assert count == 0

    def test_load_df(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DataStore(base_dir=tmpdir)
            bars = make_bars(5)
            store.save_bars(IID, bars)

            df = store.load_bars_df(IID, BarInterval.DAILY)
            assert len(df) == 5
            assert "close" in df.columns

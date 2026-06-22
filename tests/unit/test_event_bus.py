"""事件总线的单元测试。"""

from datetime import datetime

from quant_trading.core.event import Event, EventBus, EventType


class TestEventBus:
    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.BAR, handler)
        event = Event(type=EventType.BAR, data={"price": 100}, timestamp=datetime.now())
        bus.publish(event)

        assert len(received) == 1
        assert received[0].data == {"price": 100}

    def test_multiple_handlers(self):
        bus = EventBus()
        results = []

        bus.subscribe(EventType.TICK, lambda e: results.append("a"))
        bus.subscribe(EventType.TICK, lambda e: results.append("b"))

        bus.publish(Event(type=EventType.TICK, data=None))

        assert results == ["a", "b"]

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.ORDER, handler)
        bus.unsubscribe(EventType.ORDER, handler)
        bus.publish(Event(type=EventType.ORDER, data=None))

        assert len(received) == 0

    def test_subscribe_all(self):
        bus = EventBus()
        received = []

        bus.subscribe_all(lambda e: received.append(e.type))
        bus.publish(Event(type=EventType.BAR, data=None))
        bus.publish(Event(type=EventType.TICK, data=None))

        assert received == [EventType.BAR, EventType.TICK]

    def test_event_count(self):
        bus = EventBus()
        bus.subscribe(EventType.BAR, lambda e: None)

        for _ in range(5):
            bus.publish(Event(type=EventType.BAR, data=None))

        assert bus.event_count == 5

    def test_handler_error_does_not_stop_others(self):
        bus = EventBus()
        results = []

        def bad_handler(e):
            raise ValueError("oops")

        def good_handler(e):
            results.append("ok")

        bus.subscribe(EventType.BAR, bad_handler)
        bus.subscribe(EventType.BAR, good_handler)
        bus.publish(Event(type=EventType.BAR, data=None))

        assert results == ["ok"]

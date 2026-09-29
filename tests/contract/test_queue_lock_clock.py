import asyncio
from datetime import datetime

from lead_capture.adapters.clock import FrozenClock, SystemClock
from lead_capture.adapters.locks_memory import InMemoryConversationLock
from lead_capture.adapters.queue_inprocess import InProcessTurnQueue
from lead_capture.ports.clock import Clock
from lead_capture.ports.locks import ConversationLock
from lead_capture.ports.queue import TurnQueue


async def test_queue_orders_items_per_key_and_runs_keys_concurrently():
    seen: list[tuple[str, int]] = []

    async def handler(key, item):
        await asyncio.sleep(0.01 if item == 1 else 0)
        seen.append((key, item))

    q = InProcessTurnQueue()
    assert isinstance(q, TurnQueue)
    q.start(handler)
    for i in (1, 2, 3):
        await q.put("a", i)
    await q.put("b", 1)
    await q.drain()
    assert [i for k, i in seen if k == "a"] == [1, 2, 3]
    assert ("b", 1) in seen


async def test_lock_is_exclusive_per_key():
    lock = InMemoryConversationLock()
    assert isinstance(lock, ConversationLock)
    order: list[str] = []

    async def worker(name, key):
        async with lock.hold(key):
            order.append(f"{name}-in")
            await asyncio.sleep(0.01)
            order.append(f"{name}-out")

    await asyncio.gather(worker("x", "k"), worker("y", "k"))
    assert order in (["x-in", "x-out", "y-in", "y-out"], ["y-in", "y-out", "x-in", "x-out"])


def test_clocks():
    assert isinstance(SystemClock("Asia/Kolkata"), Clock)
    now = SystemClock("Asia/Kolkata").now()
    assert now.tzinfo is not None and now.utcoffset().total_seconds() == 19800
    frozen = FrozenClock(datetime(2026, 9, 29, 15, 0), "Asia/Kolkata")
    assert frozen.now().hour == 15 and frozen.now().tzinfo is not None
    frozen.advance(hours=4)
    assert frozen.now().hour == 19

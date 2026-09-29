import pytest

from lead_capture.adapters.channels.fake import FakeChannel
from tests.contract.channel_suite import (
    ASYNC_CHECKS,
    SYNC_CHECKS,
    check_choices_degrade_to_numbered_text,
)


class Ctx:
    def __init__(self):
        self.channel = FakeChannel()

    def payload(self, messages, valid=True):
        return self.channel.make_payload(messages, valid=valid)


@pytest.mark.parametrize("check", SYNC_CHECKS, ids=lambda c: c.__name__)
def test_fake_channel_contract(check):
    check(Ctx())


@pytest.mark.parametrize("check", ASYNC_CHECKS, ids=lambda c: c.__name__)
async def test_fake_channel_contract_async(check):
    await check(Ctx())


def test_numbered_text_fallback():
    check_choices_degrade_to_numbered_text()


async def test_fake_channel_records_sent():
    from lead_capture.ports.channel import OutboundMessage

    ch = FakeChannel()
    await ch.send("+91999", OutboundMessage(text="hi"))
    assert ch.sent[0][0] == "+91999" and ch.sent[0][1].text == "hi"

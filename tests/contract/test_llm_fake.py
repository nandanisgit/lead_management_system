import pytest

from lead_capture.adapters.llm.fake import FakeLLMClient
from lead_capture.ports.llm import ExtractionResult
from tests.contract.llm_client_suite import ALL_CHECKS


def factory(scenario: str) -> FakeLLMClient:
    if scenario == "timeout":
        return FakeLLMClient(timeout=True)
    if scenario == "extra_fields":
        return FakeLLMClient(
            extractions=[ExtractionResult(fields={"grade_level": "Class 9", "favourite_food": "x"})]
        )
    return FakeLLMClient(extractions=[ExtractionResult(fields={"grade_level": "Class 9"})])


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
async def test_fake_llm_contract(check):
    await check(factory)


async def test_fake_records_calls():
    client = factory("normal")
    from tests.contract.llm_client_suite import TURN

    await client.extract(TURN)
    assert client.calls == [("extract", TURN)]

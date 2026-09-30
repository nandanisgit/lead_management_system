import pytest

from tests.conftest import memory_repo
from tests.contract.lead_repository_suite import ALL_CHECKS, LEADS


class Ctx:
    def __init__(self):
        self.repo = memory_repo()

    def bad_headers_repo(self):
        return memory_repo(actual_headers={LEADS.tab: ("Wrong",)})

    def ops_write(self, lead_id, header, value):
        self.repo.ops_write(lead_id, header, value)

    def lead_values(self, lead_id):
        return self.repo.row(lead_id)

    def lead_count(self):
        return len(self.repo.leads)

    def mark_resolved(self, handoff_id):
        self.repo.mark_resolved(handoff_id)


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
def test_in_memory_repository_contract(check):
    check(Ctx())

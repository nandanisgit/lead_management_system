import pytest

from lead_capture.adapters.leads.in_memory import InMemoryLeadRepository
from tests.contract.lead_repository_suite import ALL_CHECKS


class Ctx:
    def __init__(self):
        self.repo = InMemoryLeadRepository()

    def bad_headers_repo(self):
        return InMemoryLeadRepository(lead_headers=("Wrong",))

    def ops_write(self, lead_id, column, value):
        self.repo.ops_write(lead_id, column, value)

    def lead_values(self, lead_id):
        return self.repo.row(lead_id)

    def lead_count(self):
        return len(self.repo.leads)

    def mark_resolved(self, handoff_id):
        self.repo.mark_resolved(handoff_id)


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
def test_in_memory_repository_contract(check):
    check(Ctx())

import httpx
import pytest
import respx

from lead_capture.adapters.leads.google_sheet import GoogleSheetLeadRepository
from lead_capture.ports.leads import RepositoryContractError, RepositoryUnavailable
from tests.contract.fake_sheets import BASE, SHEET_ID, FakeSheets
from tests.contract.lead_repository_suite import ALL_CHECKS, HANDOFFS, LEADS, make_lead


def repo():
    return GoogleSheetLeadRepository(
        SHEET_ID,
        lambda: "token",
        leads=LEADS,
        handoffs=HANDOFFS,
        lists_tab="Lists",
        timezone="Asia/Kolkata",
        timeout_seconds=5,
    )


class Ctx:
    def __init__(self, router):
        self.sheets = FakeSheets()
        self._active = self.sheets
        router.route(url__startswith=BASE).mock(side_effect=lambda r: self._active.handler(r))
        self.repo = repo()

    def bad_headers_repo(self):
        self._active = FakeSheets(lead_headers=("Wrong",))
        return repo()

    def ops_write(self, lead_id, header, value):
        self.sheets.set_cell(LEADS.tab, lead_id, LEADS.index(header), value)

    def lead_values(self, lead_id):
        return self.sheets.row(LEADS.tab, lead_id)

    def lead_count(self):
        return len(self.sheets.grids[LEADS.tab]) - 1

    def mark_resolved(self, handoff_id):
        self.sheets.set_cell(
            HANDOFFS.tab, handoff_id, HANDOFFS.resolved_index, HANDOFFS.resolved_value
        )


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
def test_google_sheet_repository_contract(check):
    with respx.mock(assert_all_called=False) as router:
        check(Ctx(router))


def test_append_writes_only_bot_columns():
    with respx.mock(assert_all_called=False) as router:
        ctx = Ctx(router)
        ctx.repo.append_lead(make_lead())
        assert ctx.sheets.writes == [("append", LEADS.bot_range)]


@pytest.mark.parametrize("code", [429, 500, 503])
def test_transient_errors_raise_unavailable(code):
    with respx.mock(assert_all_called=False) as router:
        ctx = Ctx(router)
        ctx.sheets.fail_next = code
        with pytest.raises(RepositoryUnavailable):
            ctx.repo.append_lead(make_lead())


def test_network_error_raises_unavailable():
    with respx.mock(assert_all_called=False) as router:
        router.route(url__startswith=BASE).mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(RepositoryUnavailable):
            repo().exists("x")


def test_permission_error_is_contract_error():
    with respx.mock(assert_all_called=False) as router:
        ctx = Ctx(router)
        ctx.sheets.fail_next = 403
        with pytest.raises(RepositoryContractError):
            ctx.repo.check_headers()


def test_sync_lists():
    with respx.mock(assert_all_called=False) as router:
        ctx = Ctx(router)
        ctx.repo.sync_lists({"Mode": ["online", "home"], "Board": ["CBSE"]})
        assert ctx.sheets.grids["Lists"] == [["Mode", "Board"], ["online", "CBSE"], ["home", ""]]


def test_header_difference_names_the_cell():
    from lead_capture.adapters.leads.google_sheet import header_difference
    from lead_capture.domain.schema import get_schema

    layout = get_schema().leads_layout()
    wrong = list(layout.headers)
    wrong[2] = "WhatsApp Number"
    assert header_difference(layout, wrong) == (
        "Leads!C1 should be 'Phone Number', found 'WhatsApp Number'"
    )
    missing_last = list(layout.headers)[:-1]
    assert "should be 'Last Updated', found None" in header_difference(layout, missing_last)
    assert "should be empty, found 'Extra'" in header_difference(
        layout, list(layout.headers) + ["Extra"]
    )

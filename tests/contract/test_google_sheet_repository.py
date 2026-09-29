import httpx
import pytest
import respx

from lead_capture.adapters.leads.google_sheet import GoogleSheetLeadRepository
from lead_capture.ports.leads import RepositoryContractError, RepositoryUnavailable
from tests.contract.fake_sheets import BASE, SHEET_ID, FakeSheets
from tests.contract.lead_repository_suite import ALL_CHECKS, make_lead


class Ctx:
    def __init__(self, router):
        self.sheets = FakeSheets()
        self._router = router
        router.route(url__startswith=BASE).mock(side_effect=self._dispatch)
        self._active = self.sheets
        self.repo = GoogleSheetLeadRepository(SHEET_ID, lambda: "token")

    def _dispatch(self, request):
        return self._active.handler(request)

    def bad_headers_repo(self):
        self._active = FakeSheets(lead_headers=("Wrong",))
        return GoogleSheetLeadRepository(SHEET_ID, lambda: "token")

    def ops_write(self, lead_id, column, value):
        self.sheets.set_cell("Leads", lead_id, column, value)

    def lead_values(self, lead_id):
        return self.sheets.row("Leads", lead_id)

    def lead_count(self):
        return len(self.sheets.grids["Leads"]) - 1

    def mark_resolved(self, handoff_id):
        self.sheets.set_cell("Handoffs", handoff_id, "I", "Resolved")


@pytest.mark.parametrize("check", ALL_CHECKS, ids=lambda c: c.__name__)
def test_google_sheet_repository_contract(check):
    with respx.mock(assert_all_called=False) as router:
        check(Ctx(router))


def test_append_writes_only_a_to_z_and_prefixes_number():
    with respx.mock(assert_all_called=False) as router:
        ctx = Ctx(router)
        ctx.repo.append_lead(make_lead())
        assert ctx.sheets.writes == [("append", "Leads!A:Z")]
        row = ctx.lead_values("L-20260929-AAAA")
        assert len(row) == 26 and row[2] == "'+919999900001" and row[25] == "NEW"


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
            GoogleSheetLeadRepository(SHEET_ID, lambda: "t").exists("x")


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

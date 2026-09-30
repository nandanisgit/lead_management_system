"""The requirement schema: every tutor-query field, defined once in config/requirement.yaml.

Why: adding or removing a field used to mean editing validation, the model's tool schema,
the questions, the summary, the sheet row and the eval checks separately. Now all of those
are generated from this one schema, so a field change is a config change. The loader also
checks the file for mistakes (unknown fields, lists or placeholders, ops columns in the
wrong place) so a bad edit stops the service at start-up instead of corrupting leads.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from lead_capture.domain.templates import placeholders
from lead_capture.ports.leads import SheetLayout

FieldType = Literal[
    "text",
    "choice",
    "multi_choice",
    "grade",
    "positive_int",
    "int_range",
    "date_or_asap",
    "email_address",
    "postal_code",
    "phone_number",
]
FLAGS = {"minor_alone"}  # conversation flags usable in conditions
LEAD_META = {
    "lead_id",
    "created_at",
    "contact",
    "language",
    "source",
    "consent_at",
    "status",
    "minor_marker",
}
HANDOFF_META = {
    "handoff_id",
    "time",
    "contact",
    "name",
    "reason",
    "captured_so_far",
    "lead_id",
    "reply_by",
}
_INT_TYPES = {"positive_int", "int_range"}


class _Strict(BaseModel):
    """Base for config models: unknown keys are errors, so typos in YAML are caught."""

    model_config = ConfigDict(extra="forbid")


class LLMHint(_Strict):
    """What the language model is told about a field in the extraction tool schema."""

    description: str = ""
    enum: bool = False  # restrict the model to the field's options


class Display(_Strict):
    """How a field's value is shown to people (summary, sheet)."""

    hide_values: list[str] = Field(default_factory=list)
    join: str = ", "


class Numbered(_Strict):
    """Parsing of numbered levels such as "9th" or "class IX" into e.g. "Class 9"."""

    format: str
    min: int
    max: int


class CopyFrom(_Strict):
    """Fill a field from another one when it is empty and ``when`` holds."""

    field: str
    when: dict | None = None


class DefaultValue(_Strict):
    """Set a fixed value when ``when`` holds (e.g. board N/A for non-school levels)."""

    value: Any
    when: dict


class FieldSpec(_Strict):
    """One tutor-requirement field. See the header of config/requirement.yaml."""

    name: str = ""
    type: FieldType
    required: bool | dict = False
    pii: bool = False
    label: dict[str, str] = Field(default_factory=dict)
    ask: dict[str, str] = Field(default_factory=dict)
    llm: LLMHint = Field(default_factory=LLMHint)
    options: list[str] = Field(default_factory=list)  # names of lists
    option_aliases: str | None = None  # name of an alias map in lists
    option_labels: dict[str, dict[str, str]] = Field(default_factory=dict)
    button_labels: dict[str, dict[str, str]] = Field(default_factory=dict)
    buttons: list[str] = Field(default_factory=list)  # lists offered as tap options
    display: Display = Field(default_factory=Display)
    min_length: int | None = None
    max_length: int | None = None
    min_items: int | None = None
    max_items: int | None = None
    min: int | None = None
    max: int | None = None
    numbered: Numbered | None = None
    digits: int | None = None
    service_area: str | dict | None = None  # "options" or {ranges: list_name}
    asap_value: str | None = None
    asap_words: str | None = None
    max_days_ahead: int | None = None
    at_least_field: str | None = None
    mirror_from: str | None = None
    copy_from: CopyFrom | None = None
    default: DefaultValue | None = None
    clear_when: dict | None = None
    # phone_number: the default country code and national number length ("91", 10)
    country_code: str | None = None
    national_digits: int | None = None
    # FR-032: pre-filled from the channel when its address is a phone number (WhatsApp),
    # otherwise asked with the channel's "share phone number" control where it has one
    channel_phone: bool = False

    @model_validator(mode="after")
    def _type_params(self) -> FieldSpec:
        """Each type needs its own parameters; fail early if one is missing."""
        needs = {
            "text": ("min_length", "max_length"),
            "choice": ("options",),
            "multi_choice": ("options", "min_items", "max_items"),
            "grade": ("options",),
            "int_range": ("min", "max"),
            "date_or_asap": ("asap_value", "asap_words", "max_days_ahead"),
            "postal_code": ("digits",),
            "phone_number": ("country_code", "national_digits"),
        }
        for param in needs.get(self.type, ()):
            if getattr(self, param) in (None, []):
                raise ValueError(f"type {self.type} needs '{param}'")
        return self


class AskGroup(_Strict):
    """Fields asked together, in order; ``ask`` is used when the whole group is missing."""

    fields: list[str]
    ask: dict[str, str] = Field(default_factory=dict)


class ServiceArea(_Strict):
    """FR-012: where home tuition is offered and what happens outside it."""

    mode_field: str
    online_value: str
    flexible_value: str
    location_fields: list[str]


class DerivedRange(_Strict):
    """A summary placeholder built from several fields (e.g. the budget range)."""

    min: str
    max: str
    unit: str
    same: str
    range: str


class SummarySpec(_Strict):
    """Lines of the confirmation summary per language."""

    derived: dict[str, DerivedRange] = Field(default_factory=dict)
    lines: dict[str, list[str]]


class Column(_Strict):
    """One sheet column: a field, a meta value, joined parts, or an ops-owned column."""

    header: str
    value: str | None = None  # "field.<name>" or "meta.<name>"
    parts: list[str] | None = None
    separator: str = " | "
    owner: Literal["bot", "ops"] = "bot"


class TabSpec(_Strict):
    """A sheet tab written by the bot (Leads, Handoffs)."""

    tab: str
    key_column: str
    created_column: str
    reply_by_column: str | None = None
    resolved_column: str | None = None
    resolved_value: str | None = None
    columns: list[Column]


class ListsColumn(_Strict):
    """A column of the Lists tab: a field's options or a named list."""

    header: str
    field: str | None = None
    list: str | None = None
    labels: str | None = None  # option_labels context, e.g. "sheet"


class ListsTab(_Strict):
    """The Lists tab that feeds the sheet's dropdowns."""

    tab: str
    columns: list[ListsColumn]


class SheetSpec(_Strict):
    """How leads and handoffs are laid out in the operations Google Sheet."""

    time_format: str
    lead_id_prefix: str
    handoff_id_prefix: str
    initial_status: str
    default_source: str
    language_labels: dict[str, str]
    minor_marker: str
    leads: TabSpec
    handoffs: TabSpec
    lists_tab: ListsTab


class RequirementSchema(_Strict):
    """The whole requirement definition, validated for internal consistency on load."""

    version: int
    lists: dict[str, Any]
    fields: dict[str, FieldSpec]
    ask_groups: list[AskGroup]
    student_key_field: str
    minor_alone_when: dict
    never_minor_when: dict | None = None
    service_area: ServiceArea
    summary: SummarySpec
    sheet: SheetSpec

    # ------------------------------------------------------------ consistency checks
    @model_validator(mode="after")
    def _consistent(self) -> RequirementSchema:
        """Reject a config that refers to things that don't exist (see module docstring)."""
        for name, spec in self.fields.items():
            spec.name = name
            for list_name in spec.options + spec.buttons:
                self._need_list(list_name, f"field {name}")
            for ref in (spec.option_aliases, spec.asap_words):
                if ref:
                    self._need_list(ref, f"field {name}")
            if isinstance(spec.service_area, dict):
                self._need_list(spec.service_area.get("ranges", ""), f"field {name}")
            for ref in (spec.at_least_field, spec.mirror_from):
                if ref:
                    self._need_field(ref, f"field {name}")
            if spec.copy_from:
                self._need_field(spec.copy_from.field, f"field {name}")
            for cond in (
                spec.required if isinstance(spec.required, dict) else None,
                spec.copy_from.when if spec.copy_from else None,
                spec.default.when if spec.default else None,
                spec.clear_when,
            ):
                if cond:
                    self._check_condition(cond.get("when", cond), f"field {name}")
        grouped = [f for g in self.ask_groups for f in g.fields]
        for f in grouped:
            self._need_field(f, "ask_groups")
        for name, spec in self.fields.items():
            if spec.required is not False and name not in grouped:
                raise ValueError(f"field {name} can be required but is in no ask_group")
        self._need_field(self.student_key_field, "student_key_field")
        self._check_condition(self.minor_alone_when, "minor_alone_when")
        if self.never_minor_when:
            self._check_condition(self.never_minor_when, "never_minor_when")
        sa = self.service_area
        for f in [sa.mode_field, *sa.location_fields]:
            self._need_field(f, "service_area")
        known = set(self.fields) | set(self.summary.derived)
        for lang, lines in self.summary.lines.items():
            for line in lines:
                self._need_placeholders(line, known, f"summary.{lang}")
        self._check_tab(self.sheet.leads, LEAD_META)
        self._check_tab(self.sheet.handoffs, HANDOFF_META)
        self._need_placeholders(self.sheet.minor_marker, set(self.fields), "sheet.minor_marker")
        for col in self.sheet.lists_tab.columns:
            if col.field:
                self._need_field(col.field, "sheet.lists_tab")
            elif col.list:
                self._need_list(col.list, "sheet.lists_tab")
            else:
                raise ValueError(f"lists_tab column {col.header} needs 'field' or 'list'")
        return self

    def _need_list(self, name: str, where: str) -> None:
        """Fail unless ``name`` is a list in ``lists:``."""
        if name not in self.lists:
            raise ValueError(f"{where}: unknown list '{name}'")

    def _need_field(self, name: str, where: str) -> None:
        """Fail unless ``name`` is a defined field."""
        if name not in self.fields:
            raise ValueError(f"{where}: unknown field '{name}'")

    def _need_placeholders(self, template: str, known: set[str], where: str) -> None:
        """Fail if a template uses placeholders that nothing provides."""
        unknown = placeholders(template) - known
        if unknown:
            raise ValueError(f"{where}: unknown placeholder(s) {sorted(unknown)}")

    def _check_condition(self, cond: dict, where: str) -> None:
        """Validate the small condition language (see config header)."""
        if "all" in cond or "any" in cond:
            for sub in cond.get("all", cond.get("any")):
                self._check_condition(sub, where)
            return
        if "flag" in cond:
            if cond["flag"] not in FLAGS:
                raise ValueError(f"{where}: unknown flag {cond['flag']}")
            return
        self._need_field(cond.get("field", ""), where)
        for key in ("in_list", "not_in_list"):
            if key in cond:
                self._need_list(cond[key], where)
        ops = {"equals", "not_equals", "in", "not_in", "in_list", "not_in_list", "is_set"}
        if not ops & set(cond):
            raise ValueError(f"{where}: condition needs one of {sorted(ops)}")

    def _check_tab(self, tab: TabSpec, meta: set[str]) -> None:
        """Columns must refer to real fields/meta, and ops columns must come last."""
        headers = [c.header for c in tab.columns]
        for required in (
            tab.key_column,
            tab.created_column,
            tab.reply_by_column,
            tab.resolved_column,
        ):
            if required and required not in headers:
                raise ValueError(f"sheet.{tab.tab}: column '{required}' not in columns")
        seen_ops = False
        for col in tab.columns:
            if col.owner == "ops":
                seen_ops = True
                continue
            if seen_ops:
                raise ValueError(f"sheet.{tab.tab}: bot column {col.header} after ops columns")
            if col.value:
                kind, _, name = col.value.partition(".")
                if kind == "field":
                    self._need_field(name, f"sheet.{tab.tab}")
                elif kind != "meta" or name not in meta:
                    raise ValueError(f"sheet.{tab.tab}: unknown value '{col.value}'")
            elif col.parts:
                for part in col.parts:
                    self._need_placeholders(part, set(self.fields) | meta, f"sheet.{tab.tab}")
            else:
                raise ValueError(f"sheet.{tab.tab}: column {col.header} needs value or parts")

    # ------------------------------------------------------------ conditions
    def evaluate(self, cond: dict | None, values: dict[str, Any], flags: dict[str, bool]) -> bool:
        """Evaluate a config condition against captured values and conversation flags."""
        if not cond:
            return True
        if "all" in cond:
            return all(self.evaluate(c, values, flags) for c in cond["all"])
        if "any" in cond:
            return any(self.evaluate(c, values, flags) for c in cond["any"])
        if "flag" in cond:
            return bool(flags.get(cond["flag"]))
        value = values.get(cond["field"])
        is_set = value not in (None, "", [])
        if "is_set" in cond:
            return is_set == bool(cond["is_set"])
        if "equals" in cond:
            return value == cond["equals"]
        if "not_equals" in cond:
            return value != cond["not_equals"]
        if "in" in cond:
            return value in cond["in"]
        if "not_in" in cond:
            return value not in cond["not_in"]
        if "in_list" in cond:
            return value in self.lists[cond["in_list"]]
        if "not_in_list" in cond:
            return value not in self.lists[cond["not_in_list"]]
        return False

    # ------------------------------------------------------------ field queries
    def field_names(self) -> list[str]:
        """All field names in processing order (the order in the config file)."""
        return list(self.fields)

    def options(self, name: str) -> list[str]:
        """Every accepted value for a choice-type field (its lists concatenated)."""
        out: list[str] = []
        for list_name in self.fields[name].options:
            out += [str(v) for v in self.lists[list_name]]
        return out

    def aliases(self, name: str) -> dict[str, str]:
        """Lower-case alternative spellings → canonical value for a field."""
        ref = self.fields[name].option_aliases
        return {k.lower(): v for k, v in (self.lists.get(ref) or {}).items()} if ref else {}

    def button_options(self, name: str) -> list[str]:
        """Values offered as tap options when this field is asked on its own ([] = none)."""
        return [str(v) for list_name in self.fields[name].buttons for v in self.lists[list_name]]

    def is_required(self, name: str, values: dict[str, Any], flags: dict[str, bool]) -> bool:
        """Whether a field must be captured before the summary, given what is known so far."""
        req = self.fields[name].required
        if isinstance(req, bool):
            return req
        return self.evaluate(req.get("when"), values, flags)

    def missing(self, values: dict[str, Any], flags: dict[str, bool]) -> list[str]:
        """Required fields still missing, in the order they should be asked."""
        order = [f for g in self.ask_groups for f in g.fields]
        return [
            f
            for f in order
            if values.get(f) in (None, "", []) and self.is_required(f, values, flags)
        ]

    def channel_phone_fields(self) -> list[str]:
        """Fields filled from, or requested through, the channel's phone number (FR-032)."""
        return [n for n, f in self.fields.items() if f.channel_phone]

    def pii_fields(self) -> set[str]:
        """Field names whose values must never appear in logs."""
        return {n for n, f in self.fields.items() if f.pii}

    def label(self, name: str, lang: str) -> str:
        """Short human label for a field (used in clarifying questions)."""
        labels = self.fields[name].label
        return labels.get(lang) or labels.get("en") or name

    def display(self, name: str, value: Any, context: str) -> Any:
        """A field value as people should see it in ``context`` ("en", "hi" or "sheet").

        Lists are joined, hidden values (e.g. board "N/A") become "", option labels are
        applied; integers stay integers for the sheet so it can calculate with them.
        """
        spec = self.fields[name]
        if value in (None, "", []):
            return ""
        if isinstance(value, list):
            labels = spec.option_labels.get(context, {})
            return spec.display.join.join(labels.get(v, v) for v in value)
        if str(value) in spec.display.hide_values:
            return ""
        if spec.type in _INT_TYPES:
            return value if context == "sheet" else str(value)
        return spec.option_labels.get(context, {}).get(str(value), str(value))

    # ------------------------------------------------------------ model tool schema
    def llm_fields_schema(self) -> dict[str, Any]:
        """JSON schema for the ``fields`` object of the model's extraction tool."""
        props: dict[str, Any] = {}
        for name, spec in self.fields.items():
            if spec.type in _INT_TYPES:
                prop: dict[str, Any] = {"type": "integer"}
            elif spec.type == "multi_choice":
                prop = {"type": "array", "items": {"type": "string"}}
            else:
                prop = {"type": "string"}
            if spec.llm.enum and spec.type == "choice":
                prop["enum"] = self.options(name)
            if spec.llm.description:
                prop["description"] = spec.llm.description
            props[name] = prop
        return {"type": "object", "properties": props, "additionalProperties": False}

    # ------------------------------------------------------------ sheet
    def _layout(self, tab: TabSpec) -> SheetLayout:
        """Turn a tab spec into the SheetLayout adapters use."""
        headers = tuple(c.header for c in tab.columns)
        return SheetLayout(
            tab=tab.tab,
            headers=headers,
            bot_columns=sum(1 for c in tab.columns if c.owner == "bot"),
            key_index=headers.index(tab.key_column),
            created_index=headers.index(tab.created_column),
            reply_by_index=headers.index(tab.reply_by_column) if tab.reply_by_column else None,
            resolved_index=headers.index(tab.resolved_column) if tab.resolved_column else None,
            resolved_value=tab.resolved_value,
            time_format=self.sheet.time_format,
        )

    def leads_layout(self) -> SheetLayout:
        """Where each lead value goes in the Leads tab (used by LeadRepository adapters)."""
        return self._layout(self.sheet.leads)

    def handoffs_layout(self) -> SheetLayout:
        """Where each handoff value goes in the Handoffs tab."""
        return self._layout(self.sheet.handoffs)

    def lists_tab(self) -> dict[str, list[str]]:
        """Dropdown values for the sheet's Lists tab, header → values."""
        out: dict[str, list[str]] = {}
        for col in self.sheet.lists_tab.columns:
            if col.field:
                values = self.options(col.field)
                labels = self.fields[col.field].option_labels.get(col.labels or "", {})
                out[col.header] = [labels.get(v, v) for v in values]
            else:
                out[col.header] = [str(v) for v in self.lists[col.list]]
        return out


def load_schema(path: Path | str) -> RequirementSchema:
    """Load and validate a requirement schema file (raises ValueError when inconsistent)."""
    return RequirementSchema.model_validate(yaml.safe_load(Path(path).read_text()))


@lru_cache(maxsize=4)
def _cached(path: str) -> RequirementSchema:
    """Load a schema file once per path."""
    return load_schema(path)


def get_schema(path: Path | str | None = None) -> RequirementSchema:
    """The schema named in settings (``schema.requirement_file``), loaded once per process."""
    if path is None:
        from lead_capture.settings import ROOT, get_settings

        path = ROOT / get_settings().schema_files.requirement_file
    return _cached(str(path))

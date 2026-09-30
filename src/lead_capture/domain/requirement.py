"""The tutee's requirement as captured so far — validated against the requirement schema.

Why: the model's extraction is only a proposal (constitution Principle II). ``apply`` runs
every proposed value through the schema's validators and cross-field rules and keeps only
what passes, so nothing unvalidated can reach the lead register. No field names are
hard-coded here: behaviour comes from config/requirement.yaml.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lead_capture.domain import field_types
from lead_capture.domain.field_types import InvalidValue
from lead_capture.domain.schema import RequirementSchema

OUT_OF_AREA = "out_of_area"


class Requirement:
    """Validated values plus the out-of-area flag; stored in ``Conversation.collected``."""

    def __init__(self, values: dict[str, Any] | None = None, out_of_area: bool = False) -> None:
        """Create from already-validated values (use ``apply`` for anything new)."""
        self.values: dict[str, Any] = dict(values or {})
        self.out_of_area = out_of_area

    # ------------------------------------------------------------ persistence
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Requirement:
        """Rebuild from the stored JSON (also accepts the older flat format)."""
        data = data or {}
        if "values" in data:
            return cls(data["values"], bool(data.get("out_of_area")))
        flat = {k: v for k, v in data.items() if k != "out_of_area" and v not in (None, [], "")}
        return cls(flat, bool(data.get("out_of_area")))

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for ``Conversation.collected``."""
        return {"values": dict(self.values), "out_of_area": self.out_of_area}

    def copy(self) -> Requirement:
        """Independent copy, so a failed update never half-changes the stored state."""
        return Requirement(
            {k: list(v) if isinstance(v, list) else v for k, v in self.values.items()},
            self.out_of_area,
        )

    # ------------------------------------------------------------ queries
    def get(self, name: str) -> Any:
        """A captured value, or None."""
        return self.values.get(name)

    def captured(self) -> dict[str, Any]:
        """All captured values (what the model sees as the current state)."""
        return {k: v for k, v in self.values.items() if v not in (None, "", [])}

    def is_minor_alone(self, schema: RequirementSchema) -> bool:
        """FR-029: does the captured data say a minor is chatting without a parent?"""
        if schema.never_minor_when and schema.evaluate(schema.never_minor_when, self.values, {}):
            return False
        return schema.evaluate(schema.minor_alone_when, self.values, {})

    def missing_required(self, schema: RequirementSchema, minor_alone: bool = False) -> list[str]:
        """Required fields still missing, in asking order."""
        return schema.missing(self.values, {"minor_alone": minor_alone})

    def is_complete(self, schema: RequirementSchema, minor_alone: bool = False) -> bool:
        """True when nothing required is missing (the summary can be shown)."""
        return not self.missing_required(schema, minor_alone)

    # ------------------------------------------------------------ updates
    def apply(
        self, proposed: dict[str, Any], schema: RequirementSchema, today: date
    ) -> tuple[Requirement, dict[str, str]]:
        """Validate proposed values; return the new requirement and {field: reason} rejects.

        Fields are processed in config order (so e.g. mode is known before the city).
        Latest valid value wins; invalid values never overwrite stored ones.
        """
        r = self.copy()
        rejected: dict[str, str] = {}
        given = {k: v for k, v in proposed.items() if k in schema.fields and v is not None}
        accepted: set[str] = set()
        for name, spec in schema.fields.items():
            if name not in given:
                continue
            try:
                value = field_types.normalise(spec, given[name], schema, today)
            except InvalidValue as exc:
                if spec.service_area == "options" and r._location_matters(schema):
                    r._outside_area(schema, name, rejected)
                elif spec.service_area != "options":
                    rejected[name] = str(exc)
                continue
            if spec.service_area and r._location_matters(schema):
                if not field_types.in_service_area(spec, value, schema):
                    r._outside_area(schema, name, rejected)
                    continue
                r.out_of_area = False
            floor = r.values.get(spec.at_least_field) if spec.at_least_field else None
            if floor is not None and value < floor:
                rejected[name] = f"must be at least {spec.at_least_field}"
                continue
            r.values[name] = value
            accepted.add(name)
        r._derive(schema, given, accepted)
        return r, rejected

    def _location_matters(self, schema: RequirementSchema) -> bool:
        """Location is only checked when the tuition is not (yet) online."""
        sa = schema.service_area
        return self.values.get(sa.mode_field) != sa.online_value

    def _outside_area(self, schema: RequirementSchema, name: str, rejected: dict) -> None:
        """FR-012: outside the service area → flexible mode becomes online, else out_of_area."""
        sa = schema.service_area
        if self.values.get(sa.mode_field) == sa.flexible_value:
            self.values[sa.mode_field] = sa.online_value
            for f in sa.location_fields:
                self.values.pop(f, None)
            self.out_of_area = False
            return
        self.out_of_area = True
        rejected[name] = OUT_OF_AREA

    def _derive(self, schema: RequirementSchema, given: dict, accepted: set[str]) -> None:
        """Apply the config's cross-field rules after each update."""
        for name, spec in schema.fields.items():
            source = self.values.get(spec.mirror_from) if spec.mirror_from else None
            fresh = spec.mirror_from in accepted and name not in given
            if source is not None and (fresh or self.values.get(name) is None):
                self.values[name] = source
            if spec.copy_from and self.values.get(name) in (None, ""):
                source = self.values.get(spec.copy_from.field)
                if source and schema.evaluate(spec.copy_from.when, self.values, {}):
                    self.values[name] = source
            if spec.default and schema.evaluate(spec.default.when, self.values, {}):
                self.values[name] = spec.default.value
            if spec.clear_when and schema.evaluate(spec.clear_when, self.values, {}):
                self.values.pop(name, None)
        if not self._location_matters(schema):
            self.out_of_area = False

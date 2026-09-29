"""One conversation turn: load → (deterministic shortcut | extract) → validate → decide → reply.

Talks only to ports (LLMClient, MessagingChannel, Clock) and the store. Constitution II: the
model proposes, RequirementState validates, and only CONFIRMING → COMPLETED creates a lead.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import update
from sqlalchemy.orm import Session

from lead_capture.conversation import fixed_texts as ft
from lead_capture.conversation import guards, planner, summary
from lead_capture.conversation.minors import update_minor_flags
from lead_capture.conversation.states import CloseReason, State, transition
from lead_capture.domain.hours import when_team_contacts
from lead_capture.domain.ids import new_lead_id
from lead_capture.domain.requirement import RequirementState
from lead_capture.ports.channel import InboundMessage, OutboundMessage
from lead_capture.ports.llm import (
    ExtractionResult,
    Instruction,
    LLMError,
    Signals,
    TranscriptLine,
    TurnContext,
)
from lead_capture.services import Services
from lead_capture.store import queries
from lead_capture.store.models import Contact, Conversation, LeadOutbox, Message

log = logging.getLogger(__name__)

TAP_PREFIXES = ("consent:", "mode:", "board:", "confirm:")
FIXED_KINDS = {"FEES_OR_TUTORS_AND_STEER", "STRICT_REDIRECT"}


@dataclass
class Turn:
    """Everything decided in one turn; replies are sent after the decision."""

    contact: Contact
    conv: Conversation
    items: list[InboundMessage]
    lang: str
    replies: list[OutboundMessage] = field(default_factory=list)
    lead_created: bool = False


class Engine:
    def __init__(self, services: Services, on_lead_created: Callable[[], None] | None = None):
        self.sv = services
        self.cfg = services.settings
        self.on_lead_created = on_lead_created

    # ------------------------------------------------------------------ entry point
    async def run_turn(self, number: str, items: list[InboundMessage]) -> None:
        items = [i for i in items if not i.is_echo]
        if not items:
            return
        with self.sv.sessions() as db:
            contact = queries.get_or_create_contact(db, number)
            conv = queries.active_conversation(db, contact.id)
            if conv is None:
                latest = queries.latest_conversation(db, contact.id)
                if latest is not None and latest.state == State.COMPLETED and contact.consent_at:
                    handled = await self._after_completion(db, contact, latest, items)
                    if handled:
                        return
                conv = self._new_conversation(db, contact, items)
            self._attach(db, conv, items)
            turn = Turn(contact, conv, items, lang=contact.language or "en")
            await self._decide(db, turn)
            db.commit()
            for reply in turn.replies:
                await self._send(db, turn, reply)
            db.commit()
        if turn.lead_created and self.on_lead_created:
            self.on_lead_created()

    # ------------------------------------------------------------------ helpers
    def _now(self):
        return self.sv.clock.now()

    def _new_conversation(self, db: Session, contact: Contact, items) -> Conversation:
        source = next((i.referral_source for i in items if i.referral_source), None) or "organic"
        state = State.IN_PROGRESS if contact.consent_at else State.AWAITING_CONSENT
        conv = queries.start_conversation(db, contact.id, source=source, state=str(state))
        if not contact.consent_at:  # before consent, only a local guess (no model call)
            contact.language = ft.guess_language(" ".join(i.text or "" for i in items))
        return conv

    def _attach(self, db: Session, conv: Conversation, items) -> None:
        ids = [i.id for i in items]
        db.execute(
            update(Message)
            .where(Message.wa_message_id.in_(ids), Message.conversation_id.is_(None))
            .values(conversation_id=conv.id)
        )
        latest = max(i.timestamp for i in items)
        conv.last_inbound_at = latest
        conv.first_inbound_at = conv.first_inbound_at or min(i.timestamp for i in items)
        if conv.state == State.STALLED:
            back = (
                State.IN_PROGRESS
                if db.get(Contact, conv.contact_id).consent_at
                else (State.AWAITING_CONSENT)
            )
            transition(conv, back)
        db.flush()

    def _taps(self, items) -> list[str]:
        return [i.choice_id for i in items if i.choice_id and i.choice_id.startswith(TAP_PREFIXES)]

    def _only_taps(self, items) -> bool:
        return all(i.choice_id and i.choice_id.startswith(TAP_PREFIXES) for i in items)

    def _deterministic(self, items) -> bool:
        return self.cfg.llm.skip_for_deterministic_turns and self._only_taps(items)

    def _context(self, db: Session, turn: Turn, state: RequirementState) -> TurnContext:
        msgs = queries.transcript(db, turn.conv.id, self.cfg.llm.context_messages)
        return TurnContext(
            transcript=[
                TranscriptLine(role="tutee" if m.direction == "in" else "assistant", text=m.body)
                for m in msgs
                if m.body
            ],
            state=state.captured(),
            missing=state.missing_required(turn.conv.minor_alone),
            language="hi" if turn.lang == "hi" else "en",
            stage=turn.conv.state,
        )

    async def _extract(self, db: Session, turn: Turn, state: RequirementState) -> ExtractionResult:
        try:
            result = await self.sv.llm.extract(self._context(db, turn, state))
        except LLMError:
            log.warning("extract_failed", extra={"conversation_id": turn.conv.id})
            return ExtractionResult(signals=Signals(understood=False))
        queries.record_usage(db, turn.conv.id, "extract", result.usage)
        if result.signals.language in ("en", "hi"):
            turn.lang = turn.contact.language = result.signals.language
        return result

    def _tap_fields(self, taps: list[str]) -> dict:
        fields: dict = {}
        for tap in taps:
            kind, _, value = tap.partition(":")
            if kind in ("mode", "board"):
                fields[kind] = value
        return fields

    # ------------------------------------------------------------------ decide
    async def _decide(self, db: Session, turn: Turn) -> None:
        conv = turn.conv
        if conv.state == State.AWAITING_CONSENT:
            await self._consent(db, turn)
        elif conv.state == State.CONFIRMING:
            await self._confirming(db, turn)
        elif conv.state == State.IN_PROGRESS:
            await self._collect(db, turn)

    async def _consent(self, db: Session, turn: Turn) -> None:
        conv, contact = turn.conv, turn.contact
        if conv.last_outbound_at is None:
            name = contact.wa_profile_name
            text = ft.text(
                "CONSENT",
                turn.lang,
                name=name,
                transcript_days=self.cfg.retention.transcript_days,
            )
            turn.replies.append(OutboundMessage(text=text, choices=ft.consent_choices(turn.lang)))
            return
        taps = self._taps(turn.items)
        extraction: ExtractionResult | None = None
        if taps and self._deterministic(turn.items):
            consent = "given" if "consent:yes" in taps else "declined"
        else:
            extraction = await self._extract(db, turn, RequirementState())
            consent = extraction.signals.consent
            if "consent:yes" in taps:
                consent = "given"
            elif "consent:no" in taps:
                consent = "declined"
        if consent == "declined":
            transition(conv, State.CLOSED, CloseReason.DECLINED_CONSENT)
            turn.replies.append(OutboundMessage(text=ft.text("CLOSE_DECLINED", turn.lang)))
            return
        if consent != "given":
            turn.replies.append(
                OutboundMessage(
                    text=ft.text("CONSENT_REASK", turn.lang),
                    choices=ft.consent_choices(turn.lang),
                )
            )
            return
        contact.consent_at = self._now()
        transition(conv, State.IN_PROGRESS)
        db.flush()
        # details the tutee gave before consenting are extracted only now (FR-005)
        has_text = queries.transcript(db, conv.id, self.cfg.llm.context_messages)
        tutee_text = [m for m in has_text if m.direction == "in" and m.type == "text"]
        if extraction is None and tutee_text:
            extraction = await self._extract(db, turn, RequirementState())
        await self._collect(db, turn, extraction=extraction, after_consent=True)

    async def _collect(
        self,
        db: Session,
        turn: Turn,
        extraction: ExtractionResult | None = None,
        after_consent: bool = False,
    ) -> None:
        conv = turn.conv
        state = RequirementState.model_validate(conv.collected or {})
        deterministic = False
        if extraction is None and not after_consent:
            if self._deterministic(turn.items):
                deterministic = True
                extraction = ExtractionResult(fields=self._tap_fields(self._taps(turn.items)))
            else:
                extraction = await self._extract(db, turn, state)
        extraction = extraction or ExtractionResult()
        fields = {**extraction.fields, **self._tap_fields(self._taps(turn.items))}
        state, rejected = state.apply(fields, self.sv.lists, self._now().date())
        conv.collected = state.model_dump()
        signals = None if deterministic else extraction.signals
        update_minor_flags(conv, state, signals, self.sv.lists)

        if signals is not None and not signals.understood and not fields:
            conv.misunderstand_streak += 1
            turn.replies.append(OutboundMessage(text=ft.text("REPHRASE", turn.lang)))
            return
        conv.misunderstand_streak = 0

        if after_consent and not fields and not state.captured():
            turn.replies.append(OutboundMessage(text=ft.text("ASK_OPEN", turn.lang)))
            return

        instruction = planner.plan(
            state,
            minor_alone=conv.minor_alone,
            rejected=rejected,
            signals=signals,
            max_questions=self.cfg.conversation.max_questions_per_message,
        )
        if instruction.kind == "SUMMARISE_AND_CONFIRM":
            self._summarise(turn, state)
            return
        await self._reply(db, turn, state, instruction, deterministic=deterministic)

    def _summarise(self, turn: Turn, state: RequirementState) -> None:
        if turn.conv.state != State.CONFIRMING:
            transition(turn.conv, State.CONFIRMING)
        text = summary.summary_text(state, turn.lang, turn.conv.minor_alone)
        turn.replies.append(OutboundMessage(text=text, choices=ft.confirm_choices(turn.lang)))

    async def _confirming(self, db: Session, turn: Turn) -> None:
        conv = turn.conv
        state = RequirementState.model_validate(conv.collected or {})
        taps = self._taps(turn.items)
        if "confirm:yes" in taps and self._only_taps(turn.items):
            self._complete(db, turn, state)
            return
        if "confirm:change" in taps and self._only_taps(turn.items):
            transition(conv, State.IN_PROGRESS)
            turn.replies.append(OutboundMessage(text=ft.text("ASK_CHANGE", turn.lang)))
            return
        extraction = await self._extract(db, turn, state)
        if extraction.fields:
            state, rejected = state.apply(extraction.fields, self.sv.lists, self._now().date())
            conv.collected = state.model_dump()
            update_minor_flags(conv, state, extraction.signals, self.sv.lists)
            if state.is_complete(conv.minor_alone) and not rejected:
                self._summarise(turn, state)
                return
            transition(conv, State.IN_PROGRESS)
            await self._collect(db, turn, extraction=ExtractionResult(signals=extraction.signals))
            return
        if extraction.signals.confirms_summary is True or "confirm:yes" in taps:
            self._complete(db, turn, state)
        elif extraction.signals.confirms_summary is False or "confirm:change" in taps:
            transition(conv, State.IN_PROGRESS)
            turn.replies.append(OutboundMessage(text=ft.text("ASK_CHANGE", turn.lang)))
        else:
            self._summarise(turn, state)

    def _complete(self, db: Session, turn: Turn, state: RequirementState) -> None:
        conv, contact = turn.conv, turn.contact
        if not state.is_complete(conv.minor_alone):  # defensive: never record an incomplete lead
            transition(conv, State.IN_PROGRESS)
            turn.replies.append(OutboundMessage(text=ft.text("ASK_CHANGE", turn.lang)))
            return
        now = self._now()
        lead_id = new_lead_id(now)
        row = summary.lead_row(
            lead_id=lead_id,
            now=now,
            timezone=self.cfg.ops.timezone,
            wa_number=contact.wa_number,
            consent_at=contact.consent_at or now,
            language=turn.lang,
            source=conv.source,
            state=state,
            minor_alone=conv.minor_alone,
        )
        db.add(LeadOutbox(lead_id=lead_id, conversation_id=conv.id, row=row.model_dump()))
        conv.lead_id = lead_id
        conv.student_key = (state.student_name or "").strip().lower()[:80]
        transition(conv, State.COMPLETED)
        when = when_team_contacts(now, self.cfg.ops)
        start = self.cfg.ops.hours_start.strftime("%-I %p")
        turn.replies.append(OutboundMessage(text=ft.close_completed(when, turn.lang, start)))
        turn.lead_created = True
        log.info("lead_confirmed", extra={"lead_id": lead_id, "conversation_id": conv.id})

    async def _after_completion(self, db: Session, contact, latest, items) -> bool:
        """A message after a completed lead: a new request, or just a thank-you."""
        self._attach(db, latest, items)
        turn = Turn(contact, latest, items, lang=contact.language or "en")
        extraction = await self._extract(db, turn, RequirementState())
        if extraction.fields or extraction.signals.new_student:
            db.execute(
                update(Message)
                .where(Message.wa_message_id.in_([i.id for i in items]))
                .values(conversation_id=None)
            )
            db.flush()
            return False
        turn.replies.append(OutboundMessage(text=ft.text("POST_COMPLETION", turn.lang)))
        db.commit()
        for reply in turn.replies:
            await self._send(db, turn, reply)
        db.commit()
        return True

    # ------------------------------------------------------------------ replies
    async def _reply(
        self,
        db: Session,
        turn: Turn,
        state: RequirementState,
        instruction: Instruction,
        deterministic: bool,
    ) -> None:
        fields = instruction.params.get("fields", [])
        choices = self._choices(fields, state, turn.lang)
        fixed_ask = self._fixed_ask(fields, state, turn.lang, instruction.params.get("clarify"))
        if instruction.kind == "FEES_OR_TUTORS_AND_STEER":
            text = f"{ft.text('FEES_OR_TUTORS', turn.lang)} {fixed_ask}"
        elif instruction.kind == "STRICT_REDIRECT":
            text = f"{ft.text('OFF_TOPIC_REDIRECT', turn.lang)} {fixed_ask}"
        elif deterministic:
            text = fixed_ask
        else:
            text = await self._model_reply(db, turn, state, instruction, fallback=fixed_ask)
        turn.replies.append(OutboundMessage(text=text, choices=choices))

    def _fixed_ask(self, fields, state: RequirementState, lang: str, clarify=None) -> str:
        ask = ft.ask_text(fields, lang, student=state.student_name)
        if clarify:
            return f"{ft.clarify_text(clarify, lang)} {ask}".strip()
        return ask

    def _choices(self, fields, state: RequirementState, lang: str):
        if fields == ["mode"]:
            return ft.mode_choices(lang)
        if fields == ["board"]:
            return ft.board_choices(self.sv.lists.boards)
        return []

    async def _model_reply(
        self, db: Session, turn: Turn, state: RequirementState, instruction: Instruction, fallback
    ) -> str:
        ctx = self._context(db, turn, state)
        tutee_texts = [ln.text for ln in ctx.transcript if ln.role == "tutee"]
        for _ in range(self.cfg.llm.max_regenerations + 1):
            try:
                result = await self.sv.llm.write_reply(ctx, instruction)
            except LLMError:
                log.warning("reply_failed", extra={"conversation_id": turn.conv.id})
                return fallback
            queries.record_usage(db, turn.conv.id, "reply", result.usage)
            issues = guards.problems(
                result.text,
                tutee_texts=tutee_texts,
                language=turn.lang,
                limits=self.cfg.conversation,
            )
            if not issues:
                return result.text
            log.info("reply_rejected", extra={"conversation_id": turn.conv.id, "issues": issues})
        return fallback

    async def _send(self, db: Session, turn: Turn, message: OutboundMessage) -> None:
        sent = await self.sv.channel.send(turn.contact.wa_number, message)
        queries.store_message(
            db, turn.contact.id, turn.conv.id, sent.id, "out", "text", message.text, self._now()
        )
        queries.record_usage(db, turn.conv.id, "message_out")
        turn.conv.last_outbound_at = self._now()

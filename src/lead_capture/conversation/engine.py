"""One conversation turn: load → (deterministic shortcut | extract) → validate → decide → reply.

Why: this is the single place where a tutee's messages turn into state changes and replies.
It talks only to ports (LLMClient, MessagingChannel, Clock) and the store, and knows no
field names — fields, questions and the summary all come from the requirement schema.
Constitution II: the model proposes, ``Requirement.apply`` validates, and only the
CONFIRMING → COMPLETED transition creates a lead.
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
from lead_capture.domain.hours import format_ist, when_team_contacts
from lead_capture.domain.ids import new_id
from lead_capture.domain.requirement import Requirement
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


@dataclass
class Turn:
    """Everything decided in one turn.

    Replies are sent only after the decision is saved, so a failed send never leaves the
    database half-updated.
    """

    contact: Contact
    conv: Conversation
    items: list[InboundMessage]
    lang: str
    replies: list[OutboundMessage] = field(default_factory=list)
    lead_created: bool = False


class Engine:
    """Runs conversation turns. One instance per process; state lives in the database."""

    def __init__(self, services: Services, on_lead_created: Callable[[], None] | None = None):
        """Build the engine from services.

        ``on_lead_created`` is called after a lead is committed, e.g. to push it to the sheet
        immediately instead of waiting for the scheduled outbox job.
        """
        self.sv = services
        self.cfg = services.settings
        self.schema = services.schema
        self.on_lead_created = on_lead_created
        self.tap_prefixes = ft.choice_prefixes(self.schema)

    # ------------------------------------------------------------------ entry point
    async def run_turn(self, number: str, items: list[InboundMessage]) -> None:
        """Handle one (debounced) batch of messages from a tutee and send the replies.

        Echoes (messages ops sent from the Business app) never trigger a turn.
        """
        items = [i for i in items if not i.is_echo]
        if not items:
            return
        with self.sv.sessions() as db:
            contact = queries.get_or_create_contact(db, number)
            conv = queries.active_conversation(db, contact.id)
            if conv is None:
                latest = queries.latest_conversation(db, contact.id)
                returning = (
                    latest is not None
                    and latest.state == State.COMPLETED
                    and contact.consent_at is not None
                )
                if returning and await self._after_completion(db, contact, latest, items):
                    return
                conv = self._new_conversation(db, contact, items)
            self._attach(db, conv, items)
            turn = Turn(contact, conv, items, lang=contact.language or "en")
            self._follow_language(turn)
            await self._decide(db, turn)
            db.commit()
            for reply in turn.replies:
                await self._send(db, turn, reply)
            db.commit()
        if turn.lead_created and self.on_lead_created:
            self.on_lead_created()

    # ------------------------------------------------------------------ helpers
    def _follow_language(self, turn: Turn) -> None:
        """Reply in the language the tutee writes in; keep it when their message is unclear."""
        text = " ".join(i.text for i in turn.items if i.type == "text" and i.text)
        detected = ft.detect_language(text)
        if detected:
            turn.lang = turn.contact.language = detected

    @staticmethod
    def _release(db: Session) -> None:
        """Save progress before a model call, so the database isn't locked while it thinks.

        SQLite allows one writer at a time. A model call can take a minute on a local model;
        holding the write lock that long makes the next webhook's insert fail with
        "database is locked". The per-contact lock still keeps turns for one tutee in order.
        """
        db.commit()

    def _now(self):
        """Current time from the Clock port (frozen in tests)."""
        return self.sv.clock.now()

    def _new_conversation(self, db: Session, contact: Contact, items) -> Conversation:
        """Start a conversation; it begins at consent unless the contact consented before."""
        referral = next((i.referral_source for i in items if i.referral_source), None)
        source = referral or self.schema.sheet.default_source
        state = State.IN_PROGRESS if contact.consent_at else State.AWAITING_CONSENT
        conv = queries.start_conversation(db, contact.id, source=source, state=str(state))
        if not contact.consent_at:  # before consent, only a local guess (no model call)
            contact.language = ft.guess_language(" ".join(i.text or "" for i in items))
        return conv

    def _attach(self, db: Session, conv: Conversation, items) -> None:
        """Link the stored messages to the conversation and update its timestamps.

        Also wakes a stalled conversation (FR-020).
        """
        ids = [i.id for i in items]
        db.execute(
            update(Message)
            .where(Message.wa_message_id.in_(ids), Message.conversation_id.is_(None))
            .values(conversation_id=conv.id)
        )
        conv.last_inbound_at = max(i.timestamp for i in items)
        conv.first_inbound_at = conv.first_inbound_at or min(i.timestamp for i in items)
        if conv.state == State.STALLED:
            consented = db.get(Contact, conv.contact_id).consent_at
            transition(conv, State.IN_PROGRESS if consented else State.AWAITING_CONSENT)
        db.flush()

    def _taps(self, items) -> list[str]:
        """Tap ids (button/list choices) in this batch that the engine understands."""
        return [i.choice_id for i in items if self._is_tap(i)]

    def _is_tap(self, item: InboundMessage) -> bool:
        """A tap on one of the options the engine offered."""
        return bool(item.choice_id and item.choice_id.startswith(self.tap_prefixes))

    def _only_taps(self, items) -> bool:
        """True when every message in the batch is a recognised tap."""
        return all(self._is_tap(i) for i in items)

    def _only_structured(self, items) -> bool:
        """True when every message is a tap or a shared phone number (nothing to interpret)."""
        return all(self._is_tap(i) or i.shared_phone for i in items)

    def _deterministic(self, items) -> bool:
        """Taps and shared numbers need no model when the cost-saving setting is on."""
        return self.cfg.llm.skip_for_deterministic_turns and self._only_structured(items)

    def _shared_fields(self, items) -> dict:
        """FR-032: a number shared with the app's contact button fills the channel-phone fields."""
        phone = next((i.shared_phone for i in reversed(items) if i.shared_phone), None)
        return {name: phone for name in self.schema.channel_phone_fields()} if phone else {}

    def _channel_fields(self, turn: Turn, req: Requirement) -> dict:
        """Values the chat app already knows, used instead of asking.

        FR-032: the phone number, when the channel address is one (WhatsApp).
        FR-033: the name, from the app's profile name (the one the greeting used).
        Only fills fields still empty; the tutee sees both in the summary and can correct them.
        """
        known: dict[str, str] = {}
        if self.sv.channel.capabilities.contact_is_phone:
            for name in self.schema.channel_phone_fields():
                known[name] = turn.contact.wa_number
        profile = (turn.contact.wa_profile_name or "").strip()
        if profile:
            for name in self.schema.channel_name_fields():
                known[name] = profile
        return {k: v for k, v in known.items() if req.get(k) in (None, "")}

    def _tap_fields(self, taps: list[str]) -> dict:
        """Field values chosen by tapping a field button ("<field>:<value>")."""
        fields: dict = {}
        for tap in taps:
            name, _, value = tap.partition(":")
            if name in self.schema.fields:
                fields[name] = value
        return fields

    def _asked(self, turn: Turn, req: Requirement) -> list[str]:
        """The fields the bot's last question asked for.

        The requirement hasn't changed since that question, so re-planning gives the same
        fields.
        """
        missing = req.missing_required(self.schema, turn.conv.minor_alone)
        return planner.next_fields(
            missing, self.schema, self.cfg.conversation.max_questions_per_message
        )

    def _short_answer(self, turn: Turn, req: Requirement, signals: Signals) -> dict:
        """A short reply the model couldn't place, read as the answer to the last question.

        Small models often miss one-word answers ("Nandani", "ICSE"). If the reply is at most
        ``conversation.short_answer_max_words`` words and not a question or a request, it is
        offered to the fields just asked: a field with fixed values (board, class, mode…) only
        if the reply is one of them; a free-text field only if it is the one text field asked.
        The value is still validated by ``Requirement.apply``.
        """
        texts = [i.text.strip() for i in turn.items if i.type == "text" and i.text]
        limit = self.cfg.conversation.short_answer_max_words
        if len(texts) != 1 or not limit:
            return {}
        text = texts[0]
        flagged = (
            signals.wants_human
            or signals.not_interested
            or signals.off_topic
            or signals.asks_fees_or_tutors
            or signals.deletion_request
            or signals.complaint_or_sensitive
            or signals.new_student
        )
        if flagged or text.endswith("?") or text.startswith("/") or len(text.split()) > limit:
            return {}
        asked = self._asked(turn, req)
        today = self._now().date()
        for name in asked:  # fixed-value fields first: the reply must be one of their values
            if self.schema.fields[name].type == "text":
                continue
            probe, rejected = req.apply({name: text}, self.schema, today)
            if not rejected and probe.get(name) not in (None, "", []):
                return {name: text}
        free_text = [n for n in asked if self.schema.fields[n].type == "text"]
        return {free_text[0]: text} if len(free_text) == 1 else {}

    def _context(self, db: Session, turn: Turn, req: Requirement) -> TurnContext:
        """Build what the model sees for this turn.

        Trimmed transcript (``llm.context_messages``), validated state, still-missing fields and
        the language — nothing unvalidated.
        """
        msgs = queries.transcript(db, turn.conv.id, self.cfg.llm.context_messages)
        asked = self._asked(turn, req) if turn.conv.state == State.IN_PROGRESS else []
        return TurnContext(
            transcript=[
                TranscriptLine(role="tutee" if m.direction == "in" else "assistant", text=m.body)
                for m in msgs
                if m.body
            ],
            state=req.captured(),
            missing=req.missing_required(self.schema, turn.conv.minor_alone),
            asked=asked,
            language="hi" if turn.lang == "hi" else "en",
            stage=turn.conv.state,
        )

    async def _extract(self, db: Session, turn: Turn, req: Requirement) -> ExtractionResult:
        """Ask the model for proposed field values and signals; record token usage.

        On model failure the turn continues as "not understood" (the tutee is asked to
        rephrase) instead of crashing.
        """
        ctx = self._context(db, turn, req)
        self._release(db)
        try:
            result = await self.sv.llm.extract(ctx)
        except LLMError:
            log.warning("extract_failed", extra={"conversation_id": turn.conv.id})
            return ExtractionResult(signals=Signals(understood=False))
        queries.record_usage(db, turn.conv.id, "extract", result.usage)
        return result

    def _apply(self, conv: Conversation, req: Requirement, fields: dict):
        """Validate proposed values into the requirement and store it on the conversation."""
        req, rejected = req.apply(fields, self.schema, self._now().date())
        conv.collected = req.to_dict()
        return req, rejected

    # ------------------------------------------------------------------ decide
    async def _decide(self, db: Session, turn: Turn) -> None:
        """Route the turn by conversation state."""
        if turn.conv.state == State.AWAITING_CONSENT:
            await self._consent(db, turn)
        elif turn.conv.state == State.CONFIRMING:
            await self._confirming(db, turn)
        elif turn.conv.state == State.IN_PROGRESS:
            await self._collect(db, turn)

    async def _consent(self, db: Session, turn: Turn) -> None:
        """FR-005: ask for consent first; nothing is extracted or stored before a yes."""
        conv, contact = turn.conv, turn.contact
        if conv.last_outbound_at is None:
            text = ft.text(
                "CONSENT",
                turn.lang,
                name=contact.wa_profile_name,
                transcript_days=self.cfg.retention.transcript_days,
            )
            turn.replies.append(ft.with_choices(text, ft.choices("consent", turn.lang), turn.lang))
            return
        taps = self._taps(turn.items)
        extraction: ExtractionResult | None = None
        if taps and self._deterministic(turn.items):
            consent = "given" if "consent:yes" in taps else "declined"
        elif not taps and self._only_structured(turn.items):  # a shared number: no answer yet
            consent = "none"
        else:
            extraction = await self._extract(db, turn, Requirement())
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
            reask = ft.text("CONSENT_REASK", turn.lang)
            turn.replies.append(ft.with_choices(reask, ft.choices("consent", turn.lang), turn.lang))
            return
        contact.consent_at = self._now()
        transition(conv, State.IN_PROGRESS)
        db.flush()
        # details the tutee gave before consenting are read only now
        earlier = queries.transcript(db, conv.id, self.cfg.llm.context_messages)
        if extraction is None and any(m.direction == "in" and m.type == "text" for m in earlier):
            extraction = await self._extract(db, turn, Requirement())
        await self._collect(db, turn, extraction=extraction, after_consent=True)

    async def _collect(
        self,
        db: Session,
        turn: Turn,
        extraction: ExtractionResult | None = None,
        after_consent: bool = False,
    ) -> None:
        """Gather requirement details.

        Validates what the tutee said, then asks for the next missing fields, or shows the
        summary when nothing required is missing.
        """
        conv = turn.conv
        req = Requirement.from_dict(conv.collected)
        deterministic = False
        if extraction is None and not after_consent:
            if self._deterministic(turn.items):
                deterministic = True
                extraction = ExtractionResult(fields=self._tap_fields(self._taps(turn.items)))
            else:
                extraction = await self._extract(db, turn, req)
        extraction = extraction or ExtractionResult()
        short = {}
        if not deterministic and not after_consent and not extraction.fields:
            short = self._short_answer(turn, req, extraction.signals)
        # what the tutee said or tapped, plus values the channel itself supplies (FR-032)
        said = {
            **short,
            **extraction.fields,
            **self._tap_fields(self._taps(turn.items)),
            **self._shared_fields(turn.items),
        }
        from_channel = self._channel_fields(turn, req)
        req, rejected = self._apply(conv, req, {**from_channel, **said})
        signals = None if deterministic else extraction.signals
        update_minor_flags(conv, req, signals, self.schema)

        if signals is not None and not signals.understood and not said:
            conv.misunderstand_streak += 1
            turn.replies.append(OutboundMessage(text=ft.text("REPHRASE", turn.lang)))
            return
        conv.misunderstand_streak = 0

        told_us = set(req.captured()) - set(from_channel)
        if after_consent and not said and not told_us:
            turn.replies.append(OutboundMessage(text=ft.text("ASK_OPEN", turn.lang)))
            return

        instruction = planner.plan(
            req,
            self.schema,
            minor_alone=conv.minor_alone,
            rejected=rejected,
            signals=signals,
            max_questions=self.cfg.conversation.max_questions_per_message,
        )
        if instruction.kind == "SUMMARISE_AND_CONFIRM":
            self._summarise(turn, req)
            return
        await self._reply(db, turn, req, instruction, deterministic=deterministic)

    def _summarise(self, turn: Turn, req: Requirement) -> None:
        """FR-013: show the code-built summary with Confirm / Change options."""
        if turn.conv.state != State.CONFIRMING:
            transition(turn.conv, State.CONFIRMING)
        text = summary.summary_text(self.schema, req, turn.lang, turn.conv.minor_alone)
        turn.replies.append(ft.with_choices(text, ft.choices("confirm", turn.lang), turn.lang))

    async def _confirming(self, db: Session, turn: Turn) -> None:
        """Handle the reply to the summary: confirm, change, or corrected values."""
        conv = turn.conv
        req = Requirement.from_dict(conv.collected)
        taps = self._taps(turn.items)
        if "confirm:yes" in taps and self._only_taps(turn.items):
            self._complete(db, turn, req)
            return
        if "confirm:change" in taps and self._only_taps(turn.items):
            transition(conv, State.IN_PROGRESS)
            turn.replies.append(OutboundMessage(text=ft.text("ASK_CHANGE", turn.lang)))
            return
        extraction = await self._extract(db, turn, req)
        if extraction.fields:
            req, rejected = self._apply(conv, req, extraction.fields)
            update_minor_flags(conv, req, extraction.signals, self.schema)
            if req.is_complete(self.schema, conv.minor_alone) and not rejected:
                self._summarise(turn, req)
                return
            transition(conv, State.IN_PROGRESS)
            await self._collect(db, turn, extraction=ExtractionResult(signals=extraction.signals))
            return
        if extraction.signals.confirms_summary is True:
            self._complete(db, turn, req)
        elif extraction.signals.confirms_summary is False:
            transition(conv, State.IN_PROGRESS)
            turn.replies.append(OutboundMessage(text=ft.text("ASK_CHANGE", turn.lang)))
        else:
            self._summarise(turn, req)

    def _complete(self, db: Session, turn: Turn, req: Requirement) -> None:
        """Record the confirmed lead and send the closing message.

        The lead goes to the outbox in the same transaction as COMPLETED; the outbox job writes
        it to the sheet exactly once.
        """
        conv, contact = turn.conv, turn.contact
        if not req.is_complete(self.schema, conv.minor_alone):  # never record an incomplete lead
            transition(conv, State.IN_PROGRESS)
            turn.replies.append(OutboundMessage(text=ft.text("ASK_CHANGE", turn.lang)))
            return
        now = self._now()
        sheet = self.schema.sheet
        lead_id = new_id(sheet.lead_id_prefix, now)
        values = summary.lead_values(
            self.schema,
            req,
            {
                "lead_id": lead_id,
                "created_at": format_ist(now, self.cfg.ops.timezone, sheet.time_format),
                "contact": contact.wa_number,
                "language": turn.lang,
                "source": conv.source,
                "consent_at": format_ist(
                    contact.consent_at or now, self.cfg.ops.timezone, sheet.time_format
                ),
            },
            minor_alone=conv.minor_alone,
        )
        db.add(LeadOutbox(lead_id=lead_id, conversation_id=conv.id, row={"values": values}))
        conv.lead_id = lead_id
        conv.student_key = str(req.get(self.schema.student_key_field) or "").strip().lower()[:80]
        transition(conv, State.COMPLETED)
        when = when_team_contacts(now, self.cfg.ops)
        start = ft.display_time(self.cfg.ops.hours_start)
        turn.replies.append(OutboundMessage(text=ft.close_completed(when, turn.lang, start)))
        turn.lead_created = True
        log.info("lead_confirmed", extra={"lead_id": lead_id, "conversation_id": conv.id})

    async def _after_completion(self, db: Session, contact, latest, items) -> bool:
        """Handle a message that arrives after a completed lead.

        A new request returns False so a new conversation starts; anything else (e.g. a
        thank-you) is answered here and returns True.
        """
        self._attach(db, latest, items)
        turn = Turn(contact, latest, items, lang=contact.language or "en")
        self._follow_language(turn)
        extraction = await self._extract(db, turn, Requirement())
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
        req: Requirement,
        instruction: Instruction,
        deterministic: bool,
    ) -> None:
        """Build the reply for an ASK-type instruction.

        Fixed text where code knows the answer (taps, fee questions, strict redirect); otherwise
        a model reply with the fixed question as fallback. Tap options are added when a field
        with buttons is asked on its own.
        """
        fields = instruction.params.get("fields", [])
        choices = ft.field_choices(fields[0], turn.lang, self.schema) if len(fields) == 1 else []
        fixed_ask = self._fixed_ask(fields, req, turn.lang, instruction.params.get("clarify"))
        if instruction.kind == "FEES_OR_TUTORS_AND_STEER":
            text = f"{ft.text('FEES_OR_TUTORS', turn.lang)} {fixed_ask}"
        elif instruction.kind == "STRICT_REDIRECT":
            text = f"{ft.text('OFF_TOPIC_REDIRECT', turn.lang)} {fixed_ask}"
        elif deterministic:
            text = fixed_ask
        else:
            text = await self._model_reply(db, turn, req, instruction, fallback=fixed_ask)
        reply = ft.with_choices(text, choices, turn.lang)
        if self.sv.channel.capabilities.can_request_phone and set(fields) & set(
            self.schema.channel_phone_fields()
        ):
            reply.phone_request_label = ft.text("SHARE_PHONE_BUTTON", turn.lang)
        turn.replies.append(reply)

    def _fixed_ask(self, fields, req: Requirement, lang: str, clarify=None) -> str:
        """The configured question for ``fields``.

        Preceded by a clarification when some values were rejected.
        """
        ask = ft.ask_text(fields, lang, self.schema, req.captured())
        if clarify:
            return f"{ft.clarify_text(clarify, lang, self.schema)} {ask}".strip()
        return ask

    async def _model_reply(
        self, db: Session, turn: Turn, req: Requirement, instruction: Instruction, fallback
    ) -> str:
        """Ask the model to phrase the reply.

        Regenerates up to ``llm.max_regenerations`` times if a guard fails, then falls back to
        the fixed text.
        """
        ctx = self._context(db, turn, req)
        tutee_texts = [ln.text for ln in ctx.transcript if ln.role == "tutee"]
        for _ in range(self.cfg.llm.max_regenerations + 1):
            self._release(db)
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
        """Send via the channel and store the outbound message (transcript + cost tracking)."""
        sent = await self.sv.channel.send(turn.contact.wa_number, message)
        queries.store_message(
            db, turn.contact.id, turn.conv.id, sent.id, "out", "text", message.text, self._now()
        )
        queries.record_usage(db, turn.conv.id, "message_out")
        turn.conv.last_outbound_at = self._now()

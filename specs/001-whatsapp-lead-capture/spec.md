# Feature Specification: WhatsApp Lead Capture

**Feature Branch**: `001-whatsapp-lead-capture`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Capture tutor-search leads from tutees over WhatsApp through a human-like conversation that gathers every requirement needed to find them a tutor, then record the confirmed lead in the operational lead register for the operations team to process." (Derived from `intent.md`, goals G1–G7.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tutee describes their need and a complete lead is recorded (Priority: P1)

A parent or student messages the business on WhatsApp saying they need a tutor. The assistant greets them, explains that their details will be stored to find a tutor and asks for a go-ahead. It then has a natural conversation — understanding free text, Hindi, Hinglish and typos, and picking up several details from a single message — asking only for what is still missing. When everything required is known, it plays back a short summary. The tutee confirms (or corrects), the lead is recorded in the operations team's lead register with status NEW, and the tutee is told when the team will get in touch.

**Why this priority**: This is the whole reason the system exists. On its own it replaces manual WhatsApp handling with complete, consistent leads the operations team can act on immediately.

**Independent Test**: Run a scripted WhatsApp conversation from consent to confirmation and check that exactly one new lead with every required field appears in the lead register, and that the tutee received the correct "what happens next" message.

**Acceptance Scenarios**:

1. **Given** a new tutee says "Hi, need a maths tutor for my son", **When** they give consent and answer the assistant's questions, **Then** the assistant asks no more than two questions per message and never asks again for a detail already given.
2. **Given** a tutee writes "Class 9 CBSE maths and science, home tuition in Dwarka, weekday evenings", **When** the assistant replies, **Then** it has captured class, board, both subjects, mode, area and schedule, and only asks for what is still missing.
3. **Given** all required details are known, **When** the assistant shows the summary and the tutee replies "change timing to weekends", **Then** the assistant updates the schedule, shows the revised summary and asks for confirmation again.
4. **Given** the tutee confirms the summary at 3 PM, **When** the lead is recorded, **Then** it appears in the lead register with status NEW and the tutee is told the team will get in touch today.
5. **Given** the tutee confirms at 7 PM (or at 8 AM), **When** the assistant closes the conversation, **Then** the tutee is told the team will reach out after 10 AM tomorrow (or today).
6. **Given** a tutee is unsure about budget, **When** asked, **Then** the assistant asks for an approximate figure they are comfortable with and never suggests a range or rate.
7. **Given** a tutee writes in Hindi or Hinglish, **When** the assistant replies, **Then** it replies in the same language.

---

### User Story 2 - Tutee drops off and comes back later (Priority: P2)

A tutee answers a few questions, goes quiet and returns hours or days later. The assistant continues from where they left off rather than starting over. A parent with two children can request a tutor for each without the details getting mixed up, and the same child never produces two active leads.

**Why this priority**: Real conversations are interrupted. Without resumption many leads are lost or duplicated, undermining the conversion target.

**Independent Test**: Start a conversation, stop half-way, resume after a simulated delay and confirm; check that one lead exists, containing details from both halves. Repeat for a second child from the same number and check that two separate leads exist.

**Acceptance Scenarios**:

1. **Given** a tutee answered class and subjects then stopped replying, **When** they message again two days later, **Then** the assistant greets them back, recaps what it already knows and asks only for the remaining details.
2. **Given** a tutee has not replied for 24 hours mid-conversation, **When** that time passes, **Then** the conversation is marked stalled and no incomplete lead appears in the lead register.
3. **Given** a parent has already confirmed a lead for one child, **When** they say "I also need a tutor for my daughter", **Then** a separate requirement is gathered for the daughter and recorded as a second lead.
4. **Given** a tutee already has an active lead for a student, **When** they start describing the same need again, **Then** the assistant recognises the existing lead instead of creating a duplicate.

---

### User Story 3 - Requests outside what the business serves (Priority: P3)

Some tutees want home tuition outside Delhi/NCR, write in a language other than English or Hindi, or decide they are not interested. The assistant handles each politely and records the outcome, without sending unserviceable requests to the operations team.

**Why this priority**: Protects the operations team from leads they cannot fulfil while still converting what can be saved (for example, moving an out-of-area home request to online classes).

**Independent Test**: Run scripted conversations for an out-of-area home request (accepting and declining online), a Tamil-language opener and an "not interested" reply; check the assistant's responses and that only the accepted-online case produces a lead.

**Acceptance Scenarios**:

1. **Given** a tutee wants home tuition in Pune, **When** they share their location, **Then** the assistant explains home tuition is available only in Delhi/NCR and offers online classes.
2. **Given** that tutee accepts online classes, **When** the conversation completes, **Then** a lead with mode "online" is recorded.
3. **Given** that tutee declines online classes, **When** the conversation ends, **Then** the conversation is closed with reason "out of area" and no lead is recorded.
4. **Given** a tutee writes in a language other than English or Hindi, **When** the assistant replies, **Then** it politely explains in English and Hindi that only these two languages are supported.
5. **Given** a tutee says they are no longer interested or asks to stop, **When** the assistant replies, **Then** it acknowledges politely, sends no further messages and closes the conversation.

---

### User Story 4 - Tutee reaches a person (Priority: P4)

At any point the tutee can ask to talk to a person. The assistant also hands over on its own when it repeatedly fails to understand, or when the tutee raises a complaint or a sensitive topic. After handover, the assistant stops replying in that conversation.

**Why this priority**: Keeps trust when automation isn't the right answer; required by intent but used by a minority of conversations.

**Independent Test**: Ask "can I talk to someone?" mid-conversation and check the handover message, that the conversation is flagged for a human, and that the assistant sends nothing further.

**Acceptance Scenarios**:

1. **Given** a conversation in progress, **When** the tutee asks to speak to a person, **Then** the assistant confirms a team member will reply, flags the conversation for human handling and stops sending automated replies.
2. **Given** the assistant has failed to understand the tutee three times in a row, **When** the next misunderstanding would occur, **Then** it hands over instead.
3. **Given** a handover happens outside 10 AM–5 PM IST, **When** the assistant confirms the handover, **Then** it tells the tutee a team member will reply after 10 AM.
4. **Given** a message contains a complaint, abuse or a sensitive topic, **When** it is received, **Then** the conversation is handed over to a human.

---

### User Story 5 - Consent, privacy and data retention (Priority: P5)

Tutees are told what is stored and why before anything is saved, and can ask for their data to be deleted. Conversation records and leads are removed automatically after their retention periods.

**Why this priority**: Legal and trust obligation (India's DPDP Act); mostly runs in the background once the core flow works.

**Independent Test**: Decline consent and check nothing is stored beyond the refusal itself; request deletion after confirming a lead and check the lead and conversation are removed; advance time past the retention periods and check automatic deletion.

**Acceptance Scenarios**:

1. **Given** a new tutee, **When** the conversation starts, **Then** the assistant explains that details will be stored to find a tutor, mentions how long they are kept, and waits for a go-ahead before collecting any details.
2. **Given** a tutee declines consent, **When** they reply "no", **Then** the assistant thanks them, collects no details and closes the conversation.
3. **Given** a tutee asks to delete their data, **When** the request is received, **Then** their leads and conversation records are deleted and they receive a confirmation.
4. **Given** a conversation record is older than 90 days, **When** the daily clean-up runs, **Then** it is deleted.
5. **Given** a lead is older than 1 year, **When** the daily clean-up runs, **Then** it and its conversation record are deleted.

---

### Edge Cases

- The tutee sends a voice note, image, sticker or document instead of text: the assistant says it can only read text messages and asks them to type the answer.
- The same WhatsApp message is delivered to the system more than once: it is processed once and never creates a duplicate reply or lead.
- The lead register is temporarily unavailable when a tutee confirms: the tutee still gets their confirmation, the lead is kept and recorded as soon as the register is available, and it is never lost.
- The tutee gives a contradictory detail later ("actually Class 10, not 9"): the latest value replaces the earlier one and is shown in the summary.
- The tutee gives a value outside the allowed lists (e.g. an unknown board or an unrecognisable class): the assistant asks a clarifying question rather than guessing.
- The tutee picks mode "either" and is outside Delhi/NCR: the lead is recorded as online.
- The tutee returns after more than 24 hours: their new message reopens WhatsApp's 24-hour service window, so the assistant replies normally and continues from the captured details. The business never messages first and sends no templates.
- A reply cannot be sent inside the window (for example the service was down for more than 24 hours after the tutee's last message): the reply is dropped and logged, the conversation stays as it is, and it resumes when the tutee writes again.
- A human agent (after handoff) must reply within 24 hours of the tutee's last message; after that neither the bot nor the team can message the tutee until they write again. With operations hours of 10 AM–5 PM every day, the worst case leaves only **7 working hours** (a last message at 5 PM means the window closes at 5 PM the next day), so each `Handoffs` row shows a reply-by time and the team works handoffs in reply-by order. Every new tutee message extends the window.
- The person chatting appears to be a minor without a parent involved (a student in Class 1–12 chatting for themselves, or other clear signs of being under 18): the assistant keeps strictly to requirement questions, asks for a parent or guardian's name and relationship before the summary, and marks the lead so the operations team contacts the parent (FR-029).
- The tutee sends many messages quickly before the assistant replies: they are treated as one turn and answered together.
- The tutee asks about fees, tutor names or availability: the assistant explains the team will share those details and continues gathering requirements.

## Requirements *(mandatory)*

### Functional Requirements

**Conversation**

- **FR-001**: System MUST converse with tutees over WhatsApp in a friendly, concise, human-like style, with at most two questions and roughly 60 words per message.
- **FR-002**: System MUST understand free-text replies in English, Hindi and Hinglish (including Hindi in Roman script) and reply in the language the tutee is using.
- **FR-003**: System MUST extract every requirement present in a message, including several in one message, and MUST NOT ask again for a detail already provided.
- **FR-004**: System MUST offer tap-to-choose options for closed choices (such as mode and board) while always accepting typed answers.
- **FR-005**: System MUST obtain the tutee's consent, after explaining what is stored, why and for how long, before collecting any details.
- **FR-006**: System MUST NOT suggest, quote or imply budget ranges, fees or rates.
- **FR-007**: System MUST briefly answer safe off-topic questions and steer back to the requirement conversation.

**Requirement capture**

- **FR-008**: System MUST collect these required details before a lead can be completed: contact name, relationship to the student (parent / student / other), student name, class or level, board or curriculum (school-level only), one or more subjects, mode (online / home / either), location (area and city, or PIN code — only for home or either), preferred days and times, start date (ASAP or a date), and budget (amount or range, per hour or per month).
- **FR-009**: System SHOULD collect these optional details when the conversation allows, without blocking completion: learning goal, sessions per week, tutor preferences (gender, language, experience), notes on current level, and an alternate email.
- **FR-010**: System MUST automatically record the tutee's WhatsApp number, WhatsApp profile name, first and last message times, the source (campaign or organic) and the time consent was given, without asking.
- **FR-011**: System MUST validate every captured value against the allowed lists (classes, boards, cities, modes, budget units) and ask a clarifying question for anything that doesn't match.
- **FR-012**: System MUST accept home tuition only for locations in Delhi/NCR (Delhi, Noida, Greater Noida, Gurugram, Ghaziabad, Faridabad); otherwise it MUST offer online classes and, if declined, close the conversation with reason "out of area".

**Confirmation and recording**

- **FR-013**: System MUST show the tutee a short summary of all captured details and let them confirm or correct it before recording the lead.
- **FR-014**: System MUST record each confirmed lead as one new entry in the operations lead register with status NEW, a unique lead ID and the creation time, and MUST record only details that passed validation and were confirmed by the tutee.
- **FR-015**: System MUST NOT record in-progress, stalled, handed-over or closed conversations in the lead register.
- **FR-016**: System MUST NOT change or remove information the operations team has entered in the lead register (status updates, assignee, notes), except for retention and deletion-on-request removals.
- **FR-017**: System MUST ensure a confirmed lead is recorded exactly once, even if messages are delivered more than once or the register is temporarily unavailable.
- **FR-018**: System MUST close each completed conversation by telling the tutee when the team will contact them, based on operations hours of 10 AM–5 PM IST every day.

**Conversation lifecycle**

- **FR-019**: System MUST track each conversation as in progress, stalled (no reply for 24 hours), handed over to a human, completed (lead recorded) or closed (with a reason: declined consent, not interested, out of area, opted out).
- **FR-020**: System MUST resume a stalled or returning conversation from the details already captured.
- **FR-021**: System MUST allow multiple leads from one WhatsApp number for different students and MUST prevent more than one active lead for the same number and student.
- **FR-022**: System MUST only send messages as replies within WhatsApp's 24-hour service window after the tutee's last message. It MUST NOT send business-initiated messages or message templates of any kind (no reminders, re-engagement, follow-ups or broadcasts). A send that would fall outside the window MUST be dropped and logged (IDs only); a tutee's new message reopens the window.

**Human handoff**

- **FR-023**: System MUST hand the conversation to a human when the tutee asks, after three consecutive failures to understand, or on complaints, abuse or sensitive topics.
- **FR-024**: After handoff, System MUST stop sending automated replies in that conversation and MUST make the handed-over conversation visible to the operations team.

**Privacy and retention**

- **FR-025**: System MUST delete a tutee's leads and conversation records on request and confirm the deletion to them.
- **FR-026**: System MUST automatically delete conversation transcripts 90 days after they were created and leads (with their conversation records) 1 year after creation.
- **FR-027**: System MUST NOT include personal details in operational logs beyond identifiers.
- **FR-028**: System MUST handle non-text messages (voice notes, images, stickers, documents) by asking the tutee to reply in text.

**Minors**

- **FR-029**: When the person chatting is a student in Class 1–12 chatting for themselves, or the conversation otherwise clearly indicates they are under 18 with no parent involved, System MUST keep strictly to requirement questions (off-topic messages get only a one-line redirect), MUST ask for a parent or guardian's name and relationship before showing the summary, and MUST mark the lead so the operations team contacts the parent or guardian. Because consent is asked before the assistant can tell it is talking to a minor, System MUST record that consent was given by the student (`consent_by_minor`) and the summary MUST ask the student to share it with their parent or guardian.

### Key Entities

- **Tutee contact**: the person chatting on WhatsApp — WhatsApp number, profile name, relationship to the student, consent time, preferred language.
- **Conversation**: one WhatsApp thread's progress — its state, the details captured so far, timestamps of last messages, handoff flag, close reason. One contact can have conversations about several students.
- **Lead**: a confirmed tutoring requirement for one student — all required and optional details, source, status (NEW, then the operations team's statuses) and creation time. Belongs to one contact; at most one active lead per contact and student.
- **Message**: one inbound or outbound WhatsApp message in a conversation, kept for 90 days as the transcript.
- **Allowed values**: the reference lists for classes, boards, cities, modes, budget units and lead statuses shared by the assistant and the operations team.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of recorded leads have every required detail filled in with a valid value.
- **SC-002**: The median completed conversation needs no more than 8 assistant messages.
- **SC-003**: In the evaluation set of scripted conversations, tutees are never asked for a detail they have already given, and budget ranges are never suggested.
- **SC-004**: At least 60% of conversations that pass the consent step end as recorded leads.
- **SC-005**: Tutees receive each reply within 5 seconds in 95% of cases.
- **SC-006**: Confirmed leads are visible to the operations team within 10 seconds of confirmation.
- **SC-007**: No confirmed lead is lost or duplicated, including when messages are delivered twice or the lead register is briefly unavailable.
- **SC-008**: 100% of requests to talk to a person result in a handover message and no further automated replies.
- **SC-009**: The operations team can start tutor search on at least 90% of new leads without contacting the tutee for missing information.

## Assumptions

- The business has an approved WhatsApp Business account and phone number. No message templates are needed: all conversations are tutee-initiated.
- The operations lead register (v1) is the team's shared spreadsheet described in `intent.md` §9.1; the team works in it directly and owns everything after status NEW.
- Human agents are members of the operations team, working the same hours (10 AM–5 PM IST, every day), and reply from the same WhatsApp number.
- A stalled conversation gets no automated reminder in v1; it simply resumes if the tutee writes again.
- Three consecutive failures to understand is a reasonable threshold for automatic handoff.
- Tutees who choose "either" mode are treated as home-tuition candidates when in Delhi/NCR and as online otherwise.
- Tutor search, matching, pricing, payments, demo scheduling and marketing broadcasts are out of scope (intent Non-goals).
- Whether India's DPDP Act requires verifiable parental consent before storing a minor's requirement is a legal question to confirm with a lawyer; v1 records the parent or guardian's details and flags the lead so the operations team contacts them (FR-029).
- The standard list of classes/levels and the budget-unit options will be finalised in the `Lists` reference during planning.

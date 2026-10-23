# Open questions: <project>

An example template for tracking a project's open questions from the impact assessment (IA), the
design specification (GDS), and intake or triage notes until each is answered and carried into the
next draft. Copy it, change it to suit the team, and point `memory/context/writing.md` at the copy.
`kit-questions extract <draft> --project <project> --write` fills it from a draft, without
duplicating questions or touching answers; `kit-questions ask` drafts the messages grouped by owner
role, and `kit-questions apply` lists the sections to update. The tracker lives at
`<project>/questions.md`. Delete the guidance lines in angle brackets when filling it in.

| Field | Value |
|---|---|
| Project | <project name> |
| Updated | <DD-Mmm-YYYY>, by <role or kit-questions> |
| Sources | <documents the questions came from, each with the DD-Mmm-YYYY it was read> |
| Classification | <internal or confidential> |

## Summary

<Counts by status (open, asked, answered, closed, superseded) and by owner role. One line on what
blocks the next draft.>

## Questions

<One row per question. Q-IDs run Q-001 and up and are never reused. Owner role, never a person's
name: requester, SRE, Cybersecurity, Compliance, AP, and so on. Asked and Due are DD-Mmm-YYYY.
Status is one of open, asked, answered, closed (the draft carries the answer), or superseded (say by
which Q-ID in the answer). Answer source says where the answer came from: an email and its date, a
meeting's minutes, or a document and section. "Answer goes to" names the IA or GDS section to
update in the next draft; a "(suggested)" entry is a keyword match for the writer to confirm.>

| Q-ID | Question | Source | Owner role | Asked | Due | Status | Answer | Answer source | Answer goes to |
|---|---|---|---|---|---|---|---|---|---|
| Q-001 | <question as asked> | <document § section, item n> | <role> | <DD-Mmm-YYYY> | <DD-Mmm-YYYY> | <status> | <answer> | <where it came from> | <IA or GDS § section> |

## How to use this tracker

- Add questions with `kit-questions extract`, or by hand with the next Q-ID.
- Send the drafts `kit-questions ask --write` saves in the project folder; Kit never sends them.
- Record answers with `kit-questions answer`, then work them into the next draft and close them.

# Safety and responsible use

Vigilix Meridian is a research and portfolio system. It is not a medical device, it has not been clinically validated, and it must not be used to make decisions about an individual patient.

## Controls in the request path

| Control | Where | What it does |
| --- | --- | --- |
| Identifier redaction | `vigilix/rag/guard.py`, before anything is logged, embedded or sent to a model | Removes NHS numbers, other identifier numbers, dates of birth, dates, emails, phone numbers, UK postcodes, record identifiers, titled names and ages above 89 |
| Crisis language | guard | First person self harm or overdose intent returns UK and US crisis support (Samaritans 116 123, NHS 111, 999, 988) instead of retrieval |
| Scope | guard | Clearly unrelated questions (elections, recipes, code) are declined unless they also contain drug safety vocabulary |
| Individual dosing | guard and pipeline | Requests for a dose for a specific patient receive a fixed notice, and the writer is told not to give a dose |
| Prompt injection | guard, applied to the question and to every retrieved passage | Instruction like text ("ignore previous instructions", role tags) is replaced before it can reach the model |
| Grounding | `vigilix/rag/llm.py` system prompt | Evidence only, one citation per sentence, disproportionality is not causation, populations stated, no doses, say when evidence is missing |
| Verification | `vigilix/rag/verifier.py` | Every sentence is checked against the evidence it cites; invented numbers, unmentioned drugs and missing citations are always marked unsupported |
| Audit | `vigilix/api/audit.py` | Append only SQLite log (triggers reject updates and deletes) storing redacted text, a hash of the original, entities, engine, verification share and confidence |

## Interpretation safeguards in the interface

* Every disproportionality result is shown with its interval, all four screening rules, its label status and a warning when it sits in a suspicious report cluster.
* Expectedness is only asserted for drugs with meaningful label coverage.
* The interaction level is labelled as heuristic triage and always paired with the underlying sentences, mechanisms and shared reaction groups.
* Causality pre fills are shown with the narrative text that justified each answer, and every answer can be changed by the assessor.
* The evaluation page lists known limitations next to the results.

## Safety probes

`vigilix/eval/answer_eval.py` runs five probes on every evaluation (crisis language, out of scope, embedded identifiers, a dosing request and a prompt injection attempt); the results are reported in `reports/answer_eval.json` and on the governance page.

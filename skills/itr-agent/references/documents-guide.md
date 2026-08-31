# The documents, and how to reconcile them

## What to gather

| Document | Where | Why |
|---|---|---|
| **Form 16** | Employer | Salary breakup, TDS, exemptions. Part B is the one with figures. |
| **AIS** (JSON) | Portal → AIS → Download | Everything the department already knows. |
| **TIS** | Same screen | The department's own *deduped* summary — the only thing that settles AIS double-reporting. |
| **Form 26AS** | Portal → e-File → View 26AS | The authoritative TDS/TCS ledger. |
| Broker Tax P&L | Zerodha Console, Groww, Upstox | Capital gains, already split by section. |
| Interest certificates | Net banking | Savings and FD interest, and any TDS. |
| Deduction proofs | You | 80C receipts, 80D premium, rent receipts. |
| Form 10E | Portal, if you had arrears | Must be **filed before** the return. |
| Form 67 | Portal, if foreign tax was withheld | Must be **filed before** the return. |

**Minimum viable set:** Form 16 + AIS. Everything else improves accuracy; those
two make a salaried return possible.

Prefer the **AIS JSON** over the PDF — the PDF is OCR-hostile and it is easy to
misread a column. The JSON download is password-protected: the password is your
PAN in lowercase followed by your date of birth as `DDMMYYYY`, with no space.

**Ask for a fresh AIS.** It fills in through the season. An AIS pulled in April
is missing most of the year's reporting.

## The reconciliation rules

**1. 26AS is authoritative for TDS.** Claim what 26AS shows, not what Form 16
shows. If 26AS shows more, some other deductor — usually a bank — withheld tax,
which means there is income you have not declared yet. Chase it.

**2. AIS double-reports; TIS does not.** The same transaction commonly appears
twice in AIS from two reporters (bank and CIB, broker and depository). TIS is the
department's deduplicated view. When AIS and TIS disagree on a total, **TIS
wins** — and if you cannot reconcile them, file AIS feedback rather than picking
the smaller number.

**3. AIS is not gospel.** It contains other people's transactions with alarming
regularity — joint accounts attributed wholly to the first holder, a namesake's
trades, a closed account still reporting. Disagreeing is fine. Doing it silently
is not: file feedback on the portal so there is a record of why your return
differs.

**4. Declare what AIS shows even if you would rather not.** A mismatch against
AIS is the single most common trigger for a s.143(1) adjustment. Undeclared
income visible in AIS is not undetected income; it is scheduled detection.

**5. Interest certificates beat memory.** "About 30,000 in FD interest" is how
returns get revised. Banks report the exact figure to AIS.

**6. Broker statements are already classified.** Zerodha and the rest split
111A / 112A / debt correctly and apply 31-Jan-2018 grandfathering. Use their
classification; do not reclassify from raw trades.

**7. Gains aggregate across brokers.** The 1,25,000 s.112A exemption is one
allowance for the year, not one per broker. Sum first, then let the engine apply
it once.

**8. Match receipts to the year they landed.** For freelancers especially — the
client deducted TDS when they paid; your invoice date is irrelevant. This is the
usual source of a 26AS-versus-books gap.

## Transcription discipline

Every figure in `return.json` is a **verbatim copy** from a document, with its
source recorded in `work/extraction-notes.md` as document, part and field. Never
write a derived number — if two figures need adding, put both in and let the
engine add them.

Then fill `source_totals` with the document-level totals **as printed**. The
validator compares your transcription against them and blocks computation on a
gap above ±10. It is the only mechanical check that a digit did not get
transposed, and it costs a minute.

## Privacy

Documents you hand to an AI agent are read by a model, which means they leave
your machine. The Python scripts here do not — they have no network access at
all.

**PAN, Aadhaar and account numbers are not needed to compute anything.** Redact
them before sharing documents, and keep them out of `return.json`; the validator
errors on a PAN pattern for exactly this reason. Type them straight into the
portal instead.

Be honest with yourself about the limit: identifiers can stay out of the loop
permanently, but every figure that feeds the return has to appear in output you
actually read. An unreviewed tax figure is a worse outcome than a seen one.

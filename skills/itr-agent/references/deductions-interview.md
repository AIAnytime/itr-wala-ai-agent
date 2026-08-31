# The deduction interview

Run this **before** computing, not after. Under the old regime an unclaimed
deduction is money left behind; under the new regime most of these do nothing —
but you cannot know which regime wins until you have the numbers, and you cannot
have the numbers until you have asked.

**Ask. Do not wait to be told.** People do not volunteer their parents' health
insurance premium, and they do not know that the employer's NPS contribution
survives the new regime.

## Rule: proofs in hand

Only figures with documentary proof go into `return.json`. Not "roughly", not
"I'm sure I paid about". If the amount is real but the proof is not to hand yet,
quantify the stake — run the engine with and without — and label it clearly as
conditional. Never let a conditional figure into the filed return.

## The questions

**s.80C — up to 1,50,000, old regime only**
EPF from your salary slip · PPF · ELSS · life-insurance premium · principal
repayment on a home loan · children's **tuition fees** (not the rest of the
school bill) · a five-year tax-saver FD · Sukanya Samriddhi · NSC.

Most salaried filers are already at the cap on EPF plus one insurance premium
and never check.

**s.80CCD(1B) — 50,000, old regime only**
Your own NPS contribution, **over and above** 80C. A genuinely separate 50,000 of
headroom that people fold into 80C by mistake.

**s.80CCD(2) — employer NPS — survives the new regime**
14% of Basic+DA in the new regime, 10% for a private employer in the old. The
only Chapter VI-A deduction that survives s.115BAC, so it is worth asking even
of someone who has already decided on the new regime. It is on your salary slip,
not your Form 16 Part B summary.

**s.80D — health insurance, old regime only**
25,000 for self, spouse and children; **another 50,000 for parents if either is a
senior citizen**. Preventive health check-ups up to 5,000 sit inside those caps.
Medical expenditure for a senior parent with no insurance also qualifies.

The parents' limb is the most commonly missed deduction in Indian returns —
partly because the premium is often paid by a sibling and partly because nobody
asks.

**s.80TTA / s.80TTB — interest**
10,000 of savings-bank interest under 60; **50,000 of savings *and* deposit
interest** at 60+. The engine applies whichever fits `age_band` — you do not
enter it. Just make sure the interest itself is in `other_sources`.

**s.80G — donations**
50% or 100%, with or without a qualifying limit depending on the institution.
Needs the 80G certificate and the donee's registration number. Cash donations
above 2,000 do not qualify at all.

**s.80E — education loan interest**
No cap on the amount, but only for 8 assessment years from the year repayment
starts. Interest only, never principal.

**s.80EEB — electric vehicle loan interest**
Up to 1,50,000, on a loan sanctioned between 1 Apr 2019 and 31 Mar 2023.

**s.80DD / s.80DDB / s.80U — disability and specified illness**
75,000 or 1,25,000 depending on severity; s.80DDB needs a prescription from a
specialist. Ask gently and once.

**s.24(b) — home loan interest**
Not Chapter VI-A — it lives in `house_property.interest_paid`. 2,00,000 on a
self-occupied property, uncapped on a let-out one (though the *loss* set-off
against other heads is capped at 2,00,000 by s.71(3A)).

**HRA — s.10(13A), old regime only**
Goes in `salary.exempt_allowances`, from Form 16. If your employer did not
process it, you can still claim it in the return with rent receipts — and a
landlord's PAN if rent exceeds 1,00,000 a year.

## Before you settle on a regime

Deductions only matter if the old regime wins. Get every one of them in first,
then run `tax_core.py` and let it compare. A half-filled deduction list makes the
new regime look better than it is, and with business income the choice is close
to permanent — Form 10-IEA, filed **before** the return, and effectively
once-in-a-lifetime.

# Knowledge-base issues

The four help pages as fetched on 2026-10-22, read line by line before sectioning
(`kb/valetax.toml`). Each issue has an id used in the section tags. The co-pilot treats
a **conflict** as a reason to send any draft that cites the section to a person, and a
**gap** as something to abstain on. These are also the content fixes with the highest
return: closing I1, I2 and I5 moves a measurable share of tickets from "needs a person"
to "draft ready" (see [evals.md](evals.md)).

| id | kind | where | what the pages say | effect on the co-pilot |
|---|---|---|---|---|
| I1 | conflict | deposit FAQ (also on the withdrawal page) | "Deposits are instant! You will be able to view your updated account balance within 60 minutes." The page intro also promises "instant" funding methods. | Instant or up to an hour? A deposit-time answer cites `funding.credit-time` and goes to a person. |
| I2 | conflict | withdrawal page, steps | The four steps are the deposit steps: step 3 "Enter your account details and amount **to deposit**", step 4 "Start Trading!". Step 2 lacks the "Withdraw" button the deposit page names for deposits. | There is no withdrawal procedure in the KB. "How do I withdraw?" goes to a person. |
| I3 | gap | verification page | 76 words, three steps. No document list, no formats, no timeline, no rejection reasons. The document list and the 48-hour figure live on the account-opening page. | Verification questions are answered from `open.documents` and `open.time`; the drafter has to cross pages. |
| I4 | gap | deposit FAQ, account-opening FAQ | "The minimum deposit starts from 8 USD, depending on the account type." The per-account amounts are on the Account types page, which is linked but not part of the KB. | "8 USD" is a floor, not an answer for a named account; "minimum for ECN?" abstains. |
| I5 | conflict | account-opening FAQ | "Opening a live account allows you to begin trading immediately" vs "Account opening and document verification will be completed within 48 hours", and live accounts require proof of identity and address. | Account-opening and verification time answers go to a person. |
| I6 | gap | all pages | Nothing on fees or commissions, payment methods by country, deposit or withdrawal limits, withdrawal processing time, a minimum withdrawal, demo accounts, or login and password help. | These are among the most common real questions. The drafter abstains; the grounding check rejects any fee or time it invents anyway. |
| I7 | conflict | withdrawal page intro vs funding FAQ | "We've made fund withdrawals easy and instant" vs a "pending" status that means "in queue … Once approved, you will be notified", and "Should you not receive your funds within 24 hours, please reach out". | Tagged on `withdraw.steps` only; the FAQ answers themselves are consistent. |

Smaller defects, kept verbatim in the KB so a citation matches the live page:

- The full funding FAQ (nine questions) appears identically on the deposit and withdrawal
  pages. Stored once, with both URLs.
- The account-opening page announces "3 quick and simple steps" and lists four.
- Typos: "in in queue", "insifficient margin", "All our account are Islamic friendly and there
  is no swap is credited or withdrawn from all trading account".
- "What leverage settings should I select?" is phrased as a request for advice. The KB answer
  is safe (it depends on strategy; up to 1:2000), but the co-pilot must not go further than that.
- "All our account are Islamic friendly" is a sweeping product claim; worth a compliance read.

## What a KB owner would do first

1. Pick one deposit-credit statement (I1) and one account-opening/verification time (I5).
2. Write the actual withdrawal steps, methods and processing times (I2, I6, I7).
3. Move the document list and verification timeline onto the verification page (I3).
4. Bring the account-types table into the KB, or link per-account minimums explicitly (I4).

Every fix is a KB edit, a new KB version hash in the traces, and a re-run of the golden set
(see [phase2.md](phase2.md), weekly loop).

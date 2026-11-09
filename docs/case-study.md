# Case study: an analysis platform for a three-person advisory firm

Every figure about the StepUp platform on this page is self-reported from my own project records.

## The problem

StepUp & Company is a three-person advisory firm. I co-founded it and was there from January 2025 to November 2026. Owners sent spreadsheets and PDFs: different layouts, different units, gaps. Turning that into a full client report took one to two weeks, mostly cleaning files and rebuilding the same analyses by hand.

## My role

I designed the process and the rules. I built the platform myself with AI coding tools. I specified what it had to do, what it must refuse to do, and how it would be tested. My two co-founders used the platform in their client work.

## What I built

- An ingestion pipeline that turns client files into clean, typed rows, each tied to where it came from.
- 46 analyses on top of those rows, including quality of earnings, working capital, pricing and valuation.
- A rule that a missing figure is flagged, never estimated. An analysis that needs a flagged figure does not run.
- AI research and drafting workflows where a second model checks the outputs against fixed criteria.
- A release gate: every change had to pass 495 database tests and a 1,198-check correctness gate. A single failed check blocked the release.

## Constraints

- Three people, so the system had to be explainable and maintainable by the same people who used it.
- Client numbers go to owners and lenders, so a silent guess was worse than a visible gap.

## What changed

- A full client report went from one to two weeks to about three days (my estimate, not a measured study).
- Gaps in client data became visible on day one instead of surfacing late in the review.

## What I would do differently

- Measure turnaround time from the start. The three-day figure is an estimate; I would log timestamps so it is evidence.
- Show clients the list of flagged items sooner, so they can fix gaps while the work is in progress.

The repository next to this file is a from-scratch, synthetic-data version of the ingestion, flagging and verification ideas. It contains no StepUp code, clients or screens.

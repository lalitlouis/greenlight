# Market

Research done 2026-08-23. Feeds the Devpost "findings and learnings" field and the Potential
Impact judging criterion.

## The bottleneck is real and it is a mandatory purchase

Script clearance is not optional. A producer cannot obtain Errors & Omissions insurance without
a clearance report, and cannot secure distribution without E&O.

| | |
|---|---|
| First full report, feature | $1,000–$3,000; $5,000+ for art-department-heavy scripts with rewrites |
| Pricing model | **per script page** |
| Turnaround | 1–10 business days; 7 days standard, priced by speed |
| Follow-up items | hourly, or ~$10 per additional item |

The pricing model is the tell: per page, tiered by turnaround, per-item follow-ups. That is
metered human labour.

## Nobody has automated it

AI has taken every adjacent task — coverage, breakdown, scheduling, storyboards (Studiovity,
AIScriptReader, ScreenplayIQ, Scriptation). Clearance itself remains manual services: The
Clearance Lab, Hollywood Script Research, Coastal Clearances, Eastern Script, No Conflict
Clearance. One 2026 survey states it directly: clearance reports remain primarily manual while AI
handles coverage, breakdown, and analysis.

Legal tech raised a record $2.4B in 2025 with 2026 outpacing it, and no script-clearance startup
surfaced in that funding data. In a category that well-funded, an unclaimed vertical is a signal.

## Why the gap exists

Clearance carries professional liability. Incumbent reports are accepted by E&O underwriters
because a named human professional stands behind them. A tool asserting "this clears" and being
wrong underwrites someone's lawsuit.

This shapes the product, not just the business model: **the citation-first design is the
liability posture.** "Here is the verbatim source, verify it" is categorically different from
"trust the model." That is why `flag.citations` has `minItems: 1` at the schema level.

## Wedges, in order of realism

1. **Pre-clearance triage** — sell to writers/producers *before* they buy the real report. Fix 40
   things for a fraction of the price. Advisory framing, no liability. This is what GREENLIGHT is.
2. **Sell to the clearance firms** — make one researcher do the work of ten; they keep liability
   and the client. This is how legal AI actually penetrated (Harvey sells to firms, not clients).
3. **Sell to E&O brokers/underwriters** — they mandate the report and carry the risk. Risk scoring
   is their native language, and the Greenlight Score speaks it.
4. **Serve who cannot buy today** — indie, streaming, branded content, games, creator work. Nobody
   pays $3k/script there. Expands the market rather than splitting it.

## Risks

- **Accuracy is existential, not a quality metric.** A wrong coverage tool is annoying; a wrong
  clearance tool is a lawsuit.
- **Thin data moat.** Workflow and corpus are replicable in a quarter by a funded team. The
  durable moat is distribution — a carrier or clearance firm as channel.
- **Services business wearing software clothing.** Failure mode is bespoke handling per customer.
- **Modest TAM at the theatrical core** (a few hundred US features/yr); only interesting with TV,
  streaming, advertising, and games layered in.

## Best next step (post-hackathon)

Call five clearance firms and two E&O brokers. One question: *"if a tool produced a first-pass
report with every claim sourced, would you use it, and would you accept it?"* The firms reveal
whether you are a tool or a threat; the brokers reveal whether the liability wall has a door.

## Sources

- https://medium.com/the-front-row-view/script-clearance-and-title-search-report-cost-448b3e761b4a
- https://theclearancelab.com/product/script-clearance-report/
- http://www.hollywoodscriptresearch.com/our-rates/
- https://www.noconflictclearance.com/pricing
- https://www.frontrowinsurance.com/errors-omissions-insurance-101
- https://scriptation.com/blog/best-ai-script-coverage-feedback-analysis/
- https://newmarketpitch.com/blogs/news/legal-ai-funding-analysis

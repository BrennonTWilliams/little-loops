---
id: 3528
title: Read the host's authoritative token counts where exposed; estimate only where they are not
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- observability
- multi-host
---

# Read the host's authoritative token counts where exposed; estimate only where they are not

## Summary

An estimated token count presented in the same column, same units, and same formatting as a measured one is an accuracy claim the project does not actually hold — and token-cost is the metric this project leads with. Model measured-vs-estimated as a per-host capability rather than an implementation detail, and surface it. Where a host exposes its own authoritative token counts, read them and delete the estimator on that path. Where it does not, keep estimating and label the number as an estimate wherever it is rendered or exported. Two hosts with two strategies and no forced uniformity is the correct outcome; a single blended number that is sometimes measured and sometimes guessed is not.

## Design

The capability belongs in the host capability map, not in an ad-hoc branch at each call site. It splits into two independently shippable halves, and the cheap one should not wait on the expensive one:

- **Labeling** (self-contained, no new ingestion required): mark estimated figures as estimates in `ll-ctx-stats` output and in anything that exports them. This removes the false precision immediately.
- **Reading authoritative counts** (lands on the host log-ingestion seam): parse a host that publishes its own token counts, prefer those over the estimator on that path, and record the measured/estimated source alongside the figure.

Where a host exposes authoritative counts, the estimator on that path is deleted rather than bypassed, so the two strategies stay visibly distinct.

## Acceptance Criteria

- [ ] `ll-ctx-stats` output labels estimated token figures as estimates, in every render and export path.
- [ ] The measured-vs-estimated strategy is modelled as a per-host capability in the host capability map, not branched per call site.
- [ ] For a host that exposes authoritative token counts, its counts are read and the estimator on that path is deleted.
- [ ] For a host that exposes no counts, estimation is kept and the figures remain labeled as estimates.
- [ ] Every rendered or exported token figure carries (or is traceable to) its source: measured or estimated.

# Upstream health comparison — October 17, 2026

Compared the deployed code, workflows, stats, and delivery ledger of:

- Upstream: `zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships`,
  snapshot `b5836d61e2437845288cc28ef0a76aed8b2691bb`.
- New-grad tracker: `apxxrv/New-Grad-Tech-Jobs`,
  snapshot `f3aacb13923574ccbbfc00182e3853dfa4d7e9b2`.

## What the baseline establishes

| Observation | Upstream | New-grad tracker |
|---|---:|---:|
| Stats data-as-of (UTC) | Oct 17, 19:36 | Oct 17, 21:43 |
| Full-registry fetch coverage | 89.3% | 89.7% |
| Attempted-board fetch success | 97.5% | 97.0% |
| Quarantined boards | 426 | 397 |
| Partial snapshots | 580 | 194 |
| Detail-enrichment requests in that run | 0 | 1,867 |
| New roles in that run | 0 | 0 |
| Native email ledger | 240 sent, 0 failed at 00:42 UTC | Empty; no email credentials configured |

These are different runs, registries, and products, not a controlled benchmark.
Upstream also has hours between scheduled starts despite the same 30-minute
cron. Its `net.py` and `health.py` are identical after the package rename.
Consequently, quarantines, result caps, and delayed scheduling are shared
limitations, not by themselves fork regressions. Result caps deliberately
prevent incomplete snapshots from closing live roles.

Sources: [upstream stats](https://zshah101.github.io/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/api/stats.json),
[new-grad stats](https://apxxrv.github.io/New-Grad-Tech-Jobs/api/stats.json).
Those endpoints continue to change; the values above identify this review's
snapshots, not a permanent status report.

## Applicable fixes

1. **Adapt upstream's one-time-enrichment cost model.** New-grad matching added
   description-based entry-level detection. Rejected detail candidates were
   discarded without recording the negative verdict, so every subsequent run
   fetched them again. A separate, versioned 24-hour negative cache fixes this
   without disabling description matching, inventing job history, or freezing
   failed/empty fetches. There is no claim that all 1,867 requests disappear.
2. **Separate source code from deployment configuration.** Upstream's email
   works because its own backend and sender are configured. Copying its mailer
   cannot transfer those credentials. The fork now reports disabled/incomplete
   delivery honestly and provides an explicitly third-party RSS-to-email
   fallback. See `CONTRIBUTING.md` for native setup.
3. **Adapt the title gate to new-grad semantics.** The shared word
   “infrastructure” admits civil/construction roles when paired with the fork's
   description fallback. Physical-role evidence now rejects infrastructure-only
   titles, while actual software/data/ML roles applied to construction survive.
   The stored listings affected by this rule are two Ferrovial Field Engineer
   postings and SpaceX's Construction Technician, Starbase Infrastructure.
4. **State the schedule, not a delivery guarantee.** README/dashboard copy
   now distinguishes the 30-minute cron from actual refresh completion.

No publish thresholds, retry policy, snapshot-completeness protections, or
publish-before-notify checks are weakened. No external scheduler, cloud
service, GitHub setting, or secret is created or changed by these fixes.

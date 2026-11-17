# Temporary guides

Short-lived guides that go with one release or one hospital's go-live: setup checklists, release testing scripts. They are not part of the numbered user guides (in the folder above), which describe how the system works for good.

Once a temporary guide's job is done (the hospital is set up, the release is tested), delete it, or move what lasts into the numbered guides.

| Guide | For | Release | Written |
| --- | --- | --- | --- |
| [Bethesda setup for versions 0.24 and 0.25](bethesda-setup-v0.25.md) | Bethesda's system administrator | v0.25.0 | 2026-11-13 |
| [Version 0.24 and 0.25 testing](v0.25-testing.md) | The hospital's testers, on the demo | v0.25.0 | 2026-11-13 |
| [Lab Worklist and Results Inbox testing](v0.27-testing.md) | The hospital's testers, on the demo | v0.27.0 | 2026-11-14 |
| [Pharmacy Worklist testing](v0.28-testing.md) | The hospital's testers, on the demo | v0.28.0 | 2026-11-15 |
| [Demo script for Bethesda](demo-script-bethesda.md) | Royce, presenting to Bethesda | v0.28.1 | 2026-11-15 |
| [Petty cash testing](petty-cash-testing.md) | The hospital's testers, on the demo | kenyan_accountant 16.8.0 | 2026-11-15 |
| [Billing approvals and Patient Bills testing](v0.29-testing.md) | The hospital's testers, on the demo | v0.29.0 | 2026-11-15 |
| [Surveillance, growth, clinical alerts and quality testing](v0.33-testing.md) | The hospital's testers, on the demo | v0.33.1 | 2026-11-16 |
| [Registration, check-in and triage changes testing](v0.34-testing.md) | Bethesda's testers, on their own system | v0.34.0 | 2026-11-16 |
| [Paying before service: consultation fee, billing desk, service points](v0.35-testing.md) | Bethesda's testers, on their own system | v0.35.0 | 2026-11-16 |
| [Consultation tabs, pharmacy substitution lock, patient receipt](v0.36-testing.md) | Bethesda's testers, on their own system | v0.36.0 | 2026-11-16 |
| [Create Bill fix and cover price books](v0.36.2-testing.md) | Bethesda's testers, on their own system | v0.36.2 | 2026-11-17 |
| [Take Payment, Cashier before service points, Billing menu](v0.37-testing.md) | Bethesda's testers, on their own system | v0.37.0 | 2026-11-17 |
| [No consultation or triage before payment](v0.41-testing.md) | Bethesda's IT team, on the demo or their own system | v0.41.0 | 2026-11-18 |
| [Bethesda go-live, 16 to 20 November](bethesda-go-live.md) | Royce's go-live team, Bethesda's coordinator and department leads | v0.29.0 | 2026-11-15 |

PDFs: `TEMPORARY=1 node make_pdfs.mjs ../temporary "<output folder>/Temporary"` from `docs/guides/tools` (same environment variables as the numbered guides).

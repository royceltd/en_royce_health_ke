# Architecture map

How `royce_health_ke` is organised, and the rules that keep it maintainable. For developers.
The code is one Frappe app; its areas are groups of modules with one job each. A module's
path is part of the app's web API (the desk calls `royce_health_ke.visits.send_to`,
`royce_health_ke.cashier.take_payment`, ...), so modules are not moved between folders to
tidy up: an area gets its own package only when it outgrows a few files, and then its
whitelisted methods keep their old paths (`override_whitelisted_methods`).

## Areas

| Area | Modules | Job |
| --- | --- | --- |
| **Patient flow** | `flow`, `visits`, `assign` | Check-in, stations, queues, every move of a patient and why (`flow` is the only code that moves one), doctor assignment |
| **Billing and payment** | `visit_bill`, `payment_status`, `cashier`, `fees`, `billing`, `bills`, `approvals`, `packages` | The visit's running bill, Create Bill, the stored payment status of every order, payment before service, Take Payment and cashier shifts, the consultation fee rule, bed and meal charges, waivers and discounts, maternity packages |
| **Insurance** | `coverage`, `schemes`, `claims` | Insurance cover per item, scheme pricebooks, claims and settlement |
| **Clinical** | `consultation`, `clinical`, `history`, `vitals`, `growth`, `cds`, `codes`, `forms` | The consultation screen, clinical records, vital signs and growth charts, clinical decision support, code sets, form layout |
| **Service points** | `lab`, `radiology`, `pharmacy`, `formulary`, `theatre`, `postop`, `tat` | Worklists and the work of the lab, radiology, pharmacy, theatre; turnaround times |
| **Maternity** | `maternity`, `lcg`, `family_planning` | ANC, labour care guide, delivery, PNC, family planning |
| **Hospital services** | `kitchen`, `laundry`, `sms` | Diet orders, linen, patient SMS |
| **Reporting** | `dashboards`, `quality`, `surveillance`, `printing` | MOH reports, dashboards, quality measures, IDSR surveillance, print formats |
| **Identity, access and security** | `identity`, `access`, `privacy`, `roles`, `security`, `compliance`, `kenya` | Patient and practitioner identity, record access log, masked details, roles, login and user safeguards, idle screen lock, the Compliance Check, Kenyan reference data |
| **Marley boundary** | `marley` | The supported Marley version, every Marley function we use, the Marley rule we replace |
| **Platform glue** | `hooks`, `sidebar`, `utils`, `setup/`, `patches/`, `demo/` | Frappe hooks, the sidebar, installation and settings defaults, data patches, the demo hospital |

## Rules (each enforced by a test)

| Rule | Why | Test |
| --- | --- | --- |
| Only `flow` moves a patient (sets the station, writes a movement) | One place answers "why is this patient here?"; every move records its Reason | `test_flow.TestOnlyFlowMovesPatients` |
| Only `marley` imports from Marley (`healthcare`) | A Marley upgrade is a checklist (`marley.USES`), not a hunt | `test_marley.test_marley_only_through_the_adapter` |
| Marley's version is the one we support | Tests run against what hospitals run | `test_marley.test_supported_version` |
| Every Marley function we use exists with the arguments we pass | An upgrade that breaks us fails a test, not a hospital | `test_marley.test_everything_we_use_exists`, `test_signatures_we_call` |
| Upgrades come first: every Marley, ERPNext or Frappe version bump goes through one checklist | Customisations never hold back an upgrade; the risky places are named | [marley-upgrade-checklist.md](marley-upgrade-checklist.md) |
| Each role's access is one matrix (`role_access.py`) | A loosened role is caught by a test before release and by the Compliance Check on a live site | `test_role_access`, Compliance Check › Access |
| Lists read the stored payment status; serving a patient checks it live | Fast worklists that agree, and no unpaid service from a stale value | `test_payment_status` |
| A new site installs cleanly | The next hospital's first day | CI (fresh site, all apps, the demo, every test) |

## Hospital rules are settings

A rule one hospital asked for becomes a switch in **Kenya Health Settings**, with the
default that hospital wanted, never code that only fits them. Defaults are set once
(`setup/install.default_settings`), so a hospital's own choice survives updates (ADR-023).
Examples: consultation fee before triage, payment before the lab / radiology / pharmacy,
cashier before the service points, insured patients paying uncovered items first.

## Releases

Every app is pinned to a tag in `deploy/apps.health.json`, the hospital release file. CI
(`.github/workflows/tests.yml`) installs those versions on a fresh site with the demo and
runs every test on each push. The image is built by GitHub Actions (`hospital-image.yml`)
and deployed with `deploy/deploy-release.sh`: the pilot server (demo and test sites) first,
then each hospital's server. See `deploy/README.md`.

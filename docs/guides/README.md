# RoyceERP Health — user guides

Step-by-step guides for hospital staff, written against the demo hospital (Kijani Valley Hospital Ltd, fictional) on hospital.royceltd.com. These files are the source of truth: change them in the same commit as the feature they describe.

| Guide | For | Last checked |
| --- | --- | --- |
| [01 Overview](01-overview.md) | Management, ICT | 2026-11-07, v0.14.0 |
| [02 Outpatient](02-outpatient.md) | Reception, triage, doctors, lab, cashier, pharmacy | 2026-11-07, v0.14.0 |
| [03 Inpatient](03-inpatient.md) | Doctors, ward nurses, pharmacy, cashier | 2026-11-07, v0.14.0 |

Planned next: Insurance (insured patient, copay, claim, rejection), Maternity, Pharmacy and stock, Cashier day-end, Administrator setup.

## Writing a guide

- One step per `##` heading: **Who**, **Where** (menu path), numbered actions, then the demo record to open and its screenshot.
- Use the demo's real record names, so a reader can open the same record.
- Say what is not built yet in one line; keep the roadmap in the overview.
- Plain words for hospital staff, not developer terms.

## Updating screenshots

Screenshots live in `images/<guide>/`; the list for each guide (record, menu path, what to scroll to or open) is in `tools/shots/<guide>.json`. Retake them after a UI change:

```bash
cd docs/guides/tools
PW=<node_modules/playwright-core> CHROME=<chromium binary> \
BASE=https://hospital.royceltd.com ADMIN_PASSWORD=<admin password> \
node capture_screenshots.js shots/outpatient.json ../images/outpatient
```

Open records through their menu path (`/desk/outpatient/...`, `/desk/inpatient/...`) so the right sidebar shows. Look at every new image before committing. The flow diagrams (`00-flow.png`) are drawn separately; redraw them when a step is added or removed.

## Demo records behind the guides

The outpatient and inpatient guides follow patients created on the demo site on 2026-11-07, after the demo loader ran: Lucy Wairimu Ndung'u (outpatient) and Mary Atieno Odhiambo (inpatient, with ward medication). They are not created by `royce_health_ke.demo.load`; a fresh demo site will have different record numbers, so update the guide text with the shots.

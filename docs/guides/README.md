# RoyceERP Health — user guides

Step-by-step guides for hospital staff, written against the demo hospital (Kijani Valley Hospital Ltd, fictional) on hospital.royceltd.com. These files are the source of truth: change them in the same commit as the feature they describe.

| Guide | For | Last checked |
| --- | --- | --- |
| [01 Overview](01-overview.md) | Management, ICT | 2026-11-11, v0.23.1 |
| [02 Outpatient](02-outpatient.md) | Reception, triage, doctors, lab, cashier, pharmacy | 2026-11-11, v0.23.1 |
| [03 Inpatient](03-inpatient.md) | Doctors, ward nurses, pharmacy, cashier | 2026-11-11, v0.23.1 |
| [04 Insurance](04-insurance.md) | Reception, cashier, claims officer, finance | 2026-11-11, v0.23.1 |
| [05 Maternity](05-maternity.md) | ANC nurses, midwives, MCH, cashier | 2026-11-11, v0.23.1 |
| [06 Pharmacy and stock](06-pharmacy-and-stock.md) | Pharmacist, stores | 2026-11-11, v0.23.1 |
| [07 Cashier day-end](07-cashier-day-end.md) | Cashier, accountant | 2026-11-11, v0.23.1 |
| [08 Administrator setup](08-administrator-setup.md) | System administrator | 2026-11-11, v0.23.1 |
| [09 Patient SMS](09-patient-sms.md) | Reception, clinical staff, administrator | 2026-11-08, v0.15.1 |
| [10 Theatre](10-theatre.md) | Surgeons, anaesthetists, theatre and ward nurses | 2026-11-11, v0.23.1 |
| [11 Theatre testing](11-theatre-testing.md) | The hospital's testers, before go-live | 2026-11-11, v0.23.1 |
| [12 Reception, queue and billing](12-reception-queue-billing.md) | Reception, triage, cashier, lab, pharmacy, managers | 2026-11-11, v0.23.1 |
| [13 Reception and billing testing](13-reception-billing-testing.md) | The hospital's testers, before go-live | 2026-11-11, v0.23.1 |
| [14 Version 0.22 testing](14-v0.22-testing.md) | The hospital's testers: residence, consultation, pricebooks, insured billing, cashiers, TAT | 2026-11-11, v0.23.1 |

Planned next: radiology, emergency, kitchen and laundry, MOH reporting for the HRIO.

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

The Patient SMS shots (09) click through dialogs and really send, so they have their own script, `tools/capture_sms.js`, run against a local demo site whose Bulk SMS Settings point at a mock RoyceTalk API (never a live key). The other demo sites don't have royce_talk.

Open records through their menu path (`/desk/outpatient/...`, `/desk/inpatient/...`) so the right sidebar shows. Look at every new image before committing. The flow diagrams (`00-flow.png`) are drawn separately; redraw them when a step is added or removed.

## Making the client PDFs

`tools/make_pdfs.mjs` turns all the guides into A4 PDFs with a Royce cover line, page numbers and full-resolution screenshots:

```bash
cd docs/guides/tools
NODE_MODULES=<node_modules with micromark, micromark-extension-gfm, playwright-core> \
CHROME=<chromium binary> \
node make_pdfs.mjs .. "<output folder>"
```

`ONLY=09` builds just that guide.

Add new guides to its list and update its "Guide checked" date when the guides are re-checked.

## Demo records behind the guides

Insurance, maternity and theatre follow the demo loader's patients (Peter Otieno Kamau, Faith Njeri Wambui, Daniel Mutua Kioko). The outpatient, inpatient, pharmacy, cashier and administrator guides also use records created on the demo site on 2026-11-07 after the loader ran: Lucy Wairimu Ndung'u (outpatient), Mary Atieno Odhiambo (inpatient, with ward medication), a supplier delivery, a stock count, the M-Pesa settlement and two staff users. They are not created by `royce_health_ke.demo.load`; a fresh demo site will have different record numbers, so update the guide text with the shots.

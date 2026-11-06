## RoyceERP Health (royce_health_ke)

The Kenyan layer for hospitals on [Marley Health](https://github.com/earthians/marley) (`healthcare`, branch `version-16`) and ERPNext v16. Registered with DHA AfyaConnect as **RoyceERP Health v1.0**.

It adds what a Kenyan hospital needs on top of Marley: SHA claims through DHA's Health Information Exchange, private insurance (Slade360 and insurers), maternity, theatre, MOH reports (705A/B, 717, 711, 710) and KHIS, and Kenyan identifiers and code sets. It works alongside the other RoyceERP apps when they are installed: `kenyan_accountant` (chart of accounts, VAT), `royce_etims` (KRA eTIMS), `royce_payments` (M-Pesa) and `royce_payroll_ke` (PAYE, SHIF, Housing Levy).

### Status

| Workstream | State |
|---|---|
| 0. Foundation: app, Marley fixes, demo loader | Done |
| 1. Kenyan identifiers and code sets (ICD-11/10, LOINC, PPB) | Next |
| 2. SHA / HIE connector | Waiting for AfyaConnect sandbox approval |
| 3. Billing and private insurance | Planned |
| 4. Maternity, 5. Theatre, 6. Radiology | Planned |
| 7. MOH reports, KHIS, dashboards | Planned |
| 8. Kitchen, laundry | Planned |
| 9. Go-live readiness | Planned |

### Installation

```bash
bench get-app --branch version-16 https://github.com/earthians/marley
bench get-app royce_health_ke
bench --site <site> install-app erpnext healthcare royce_health_ke
```

Install the other RoyceERP apps first if the hospital uses them. A company must exist before `kenyan_accountant` and `royce_payroll_ke` can set it up: run their `provision(company)` after the setup wizard.

### Marley fixes

Applied after install and every migrate, only where still broken (`royce_health_ke/setup/marley_fixes.py`):

- Patient History Settings ships Lab Test's comment field as a table, which crashes the submit of any lab test with a comment. The field types are re-read from the doctype.

### Demo

A fictional private hospital, **Kijani Valley Hospital Ltd**, and one patient's journey: registration, triage, consultation, cashier (M-Pesa), lab, admission, ward round, final bill with pharmacy dispensing, discharge. Receipts are signed with KRA eTIMS when the company has eTIMS active.

```bash
bench --site <demo-site> set-config royce_health_demo 1
bench --site <demo-site> execute royce_health_ke.demo.load
```

The loader refuses to run unless the site opts in, so it can't touch a client's live data. It is safe to run again.

### License

MIT (scaffold default). Under review: Marley Health is GPL-3.0.

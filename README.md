## RoyceERP Health (royce_health_ke)

The Kenyan layer for hospitals on [Marley Health](https://github.com/earthians/marley) (`healthcare`, branch `version-16`) and ERPNext v16. Registered with DHA AfyaConnect as **RoyceERP Health v1.0**.

It adds what a Kenyan hospital needs on top of Marley: SHA claims through DHA's Health Information Exchange, private insurance (Slade360 and insurers), maternity, theatre, MOH reports (705A/B, 717, 711, 710) and KHIS, and Kenyan identifiers and code sets. It works alongside the other RoyceERP apps when they are installed: `kenyan_accountant` (chart of accounts, VAT), `royce_etims` (KRA eTIMS), `royce_payments` (M-Pesa) and `royce_payroll_ke` (PAYE, SHIF, Housing Levy).

### Status

| Workstream | State |
|---|---|
| 0. Foundation: app, Marley fixes, demo loader | Done |
| 1. Kenyan identifiers and code sets (ICD-11/10, LOINC, PPB) | Done (ICD-10, LOINC, PPB lists to load from source files) |
| 2. SHA / HIE connector | Waiting for AfyaConnect sandbox approval |
| 3. Billing and private insurance | Done: bed nights, insured visits on Marley's model, claim rejections. Slade360 and separate insurer invoices pending |
| 4. Maternity | ANC, labour and delivery, newborn, PNC done (to align with the client's forms); maternity billing packages pending |
| 5. Theatre | Booking, consent, WHO checklist, anaesthesia record, operation note done |
| 6. Radiology | Worklist, perform/report/verify, accession numbers, MOH 717 imaging done; PACS/modality integration pending |
| 7. MOH reports, KHIS, dashboards | MOH 705A/B and 717 done (mappings to confirm with the HRIO); KHIS submission and dashboards pending |
| 8. Kitchen, laundry | Planned |
| 9. Go-live readiness | Planned |

### Installation

```bash
bench get-app --branch version-16 https://github.com/earthians/marley
bench get-app royce_health_ke
bench --site <site> install-app erpnext healthcare royce_health_ke
```

Install the other RoyceERP apps first if the hospital uses them. A company must exist before `kenyan_accountant` and `royce_payroll_ke` can set it up: run their `provision(company)` after the setup wizard.

### Kenyan identifiers

- **Patient:** ID type and number (copied to Marley's unique UID, duplicates refused with the existing patient named), SHA member number, Client Registry ID (from the HIE), county and sub-county, next of kin. Kenyan phone numbers are normalised to +254.
- **Healthcare Practitioner:** cadre, regulator (KMPDC, NCK, COC, PPB, KMLTTB), registration and practising licence numbers, licence expiry, Health Worker Registry ID (from the HIE). Healthcare Administrators get a notification 30, 14, 7 and 1 day(s) before a licence expires, then weekly once expired.
- **Health Facility** (new): one per site - company, KEPH level, KMHFL code, SHA facility code, county, branch (and so the eTIMS branch), service unit group.

### Code sets

Stored in Marley's Code System / Code Value, FHIR-shaped (system URI + code + display) for the HIE.

| Code system | Source | Load with |
|---|---|---|
| ICD-11 MMS | WHO, downloaded at setup (CC BY-ND 3.0 IGO, not bundled) | `bench --site <site> execute royce_health_ke.codes.sync_icd11` (35,664 codes, about 5 s) |
| ICD-10 | WHO ICD-10 file the hospital holds | `royce_health_ke.codes.import_csv("ICD-10", <file url>)` |
| LOINC | LoincTableCore.csv (free loinc.org account) | `import_csv("LOINC", <file url>, "LOINC_NUM", "LONG_COMMON_NAME")` |
| PPB product codes | Pharmacy and Poisons Board register | `import_csv("PPB Product Code", <file url>)` |

`royce_health_ke.codes.set_coding(doc, system, code)` attaches a code to a Diagnosis, Lab Test Template or Medication.

### Billing and insurance

- **Bed charge basis** (Kenya Health Settings): *Per night* (default) charges one bed day per midnight in the ward, at least one; *Per 24 hours* keeps Marley's hours / 24.
- **Insured patients** use Marley's model: services ordered under a policy get a Patient Insurance Coverage (automatic, or manual = pre-authorisation); the patient's invoice carries the insurer's share per line and a journal entry moves it to the insurer's claims receivable, so the cashier collects only the copay. One eTIMS invoice, to the patient, for the full amount.
- **Insurance Claim** per visit: approve or reject each line, then the insurer's payment.
- **Rejected lines** (missing in Marley): *Settle Rejected Lines* on the claim either bills the patient (no new eTIMS invoice needed) or writes the amount off to the insurer's Rejected Claims expense account. Cancelling the settlement entry reopens the line.

Open: whether insurers need an eTIMS invoice addressed to them (separate insurer invoice), pending a tax adviser's view; Slade360 integration pending API access.

### Maternity

- **Pregnancy Record**: one per pregnancy - LMP and EDD (LMP + 280 days), gravida/parity, booking screening (blood group, Hb, HIV, syphilis, hepatitis B), risk factors, status.
- **ANC Visit**: contact number and gestation worked out; examination, IPTp-SP, Td, iron/folate, ITN, danger signs.
- **Delivery Record**: labour observations with WHO Labour Care Guide alerts (FHR, pulse, BP, temperature, contractions, liquor), mode of delivery, uterotonic, blood loss, perineum, complications (APH, PPH, eclampsia, ruptured uterus, obstructed labour, sepsis), mother's condition, and the babies (weight, APGAR, outcome, essential newborn care). On submit, each live-born baby gets a Patient record linked to the mother.
- **PNC Visit**: visit number and MOH timing bucket (within 48 hours / 3 days to under 6 weeks / after).
- MOH 717 now counts ANC and PNC visits, deliveries by mode, births, stillbirths, neonatal deaths, low birth weight and maternal deaths.

Fields follow the MOH ANC, maternity and PNC registers (as in KenyaEMR) - align with the hospital's own forms.

### Theatre

Around Marley's Clinical Procedure (which carries the procedure's price and consumables):

- **Theatre Booking**: theatre (a service unit whose type is an OT), scheduled start and duration, surgeon, assistant, anaesthetist, priority, insurance pre-authorisation. Clashes on the theatre, surgeon, anaesthetist or patient are refused.
- **Surgical Consent** (submitted): what was explained, risks, alternatives, anaesthesia and transfusion consent, who consented, witness, scanned form.
- **Surgical Safety Checklist**: the WHO Sign In, Time Out and Sign Out items; each phase is Done when every item is answered, only after the one before, and time-stamped.
- **Anaesthesia Record** (submitted): ASA class, technique, airway, drugs and intra-operative vitals, fluids and losses, Aldrete score at recovery discharge.
- **Operation note** on the Clinical Procedure: indication, findings, procedure details, blood loss, specimens, implants, complications, post-op instructions.
- **Into Theatre** needs submitted consent, Sign In done and no pending/declined pre-authorisation (an emergency may proceed while pending); it creates and starts the Clinical Procedure. **Complete** needs Time Out, Sign Out and the operation note; it completes the procedure and issues its consumables from the theatre's warehouse.
- **Theatre List** report: the day's list per theatre with consent, checklist and anaesthesia status.

### Radiology

Built on Marley's imaging Observations (Observation Template category *Imaging*, ordered from an encounter like a lab test):

- Templates carry a **Modality** and the **MOH 717 Imaging Row** they count in.
- Each imaging observation gets an **accession number** (RAD-YYYYMMDD-####) and an exam status: *Requested* -> **Exam Performed** (radiographer, contrast, dose, images or PACS link) -> **Report** (findings into Marley's result, impression, radiologist) -> **Verify and Release** (status Final, submitted, service request completed).
- **Radiology Worklist** report: open exams, STAT and urgent first, with waiting time.
- MOH 717 imaging rows count exams performed in the month.

DICOM/HL7 integration with the hospital's X-ray and ultrasound equipment comes once their equipment is known; until then images are attached or linked.

### MOH reports

- **MOH 705 Outpatient Summary** (705A under 5 / 705B 5 and over): one row per indicator, days 1-31 and total. Rows are **MOH 705 Indicator** records, mapped to ICD-10/ICD-11 code prefixes, specific Diagnoses or lab tests, so the Health Records Officer can correct them. A diagnosis counts on its longest matching prefix; unmatched ones go to "All other diseases". New cases only (once per patient per indicator per month); first attendance = first outpatient day of the calendar year.
- **MOH 717 Service Workload**: outpatient attendances by clinic, sex and age; laboratory tests; admissions, discharges, deaths, abscondees and referrals per ward category. Maternity, MCH, procedures and imaging rows are listed as "Not captured yet" until those modules exist.
- Set the **MOH 717 Clinic** on Medical Departments, the **MOH 717 Ward** on inpatient Service Unit Types, and the **Discharge Outcome** on Inpatient Records.

The default 705 mappings are Royce's first pass from the KenyaEMR specification (palladiumkenya/openmrs-module-kenyaemr, MPL 2.0, read only) - review them with the hospital's HRIO against the current MOH forms.

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

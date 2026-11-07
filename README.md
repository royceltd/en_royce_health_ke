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
| 4. Maternity | ANC, labour and delivery, newborn, PNC, family planning, maternity packages done (to align with the client's forms) |
| 5. Theatre | Booking, consent, WHO checklist, anaesthesia record, operation note done |
| 6. Radiology | Worklist, perform/report/verify, accession numbers, MOH 717 imaging done; PACS/modality integration pending |
| 7. MOH reports, KHIS, dashboards | MOH 705A/B, 706, 711 and 717 done (mappings to confirm with the HRIO and lab); management dashboards done; KHIS submission pending. MOH 710 not needed by the first client |
| 8. Kitchen, laundry | Diet orders, ward diet list, meal charges; linen movements and status done |
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
- **Delivery Record**: the MOH Modified WHO Labour Care Guide - each labour observation records supportive care (companion, pain relief, oral fluid, posture), baby (baseline FHR, decelerations, amniotic fluid, position, caput, moulding), woman (pulse, BP, temperature, urine protein/acetone), labour progress (contractions and their duration, cervix, descent, pushing), shared decision-making (assessment, action plan), oxytocin and IV fluids, and initials. Every value meeting the guide's ALERT column is flagged, plus the cervix lag-time alert (no progress for 6 h at 5 cm, 5 h at 6, 3 h at 7, 2.5 h at 8, 2 h at 9). The FHR alert floor is in Kenya Health Settings (110, WHO; set 120 if the facility's form says so). The form shows the chart laid out like the paper guide, and **Print Labour Care Guide** prints it (12 observations per page, alerts circled). Header: active labour diagnosis and membrane rupture times, with parity, LNMP, PMTCT, syphilis and hepatitis B from the Pregnancy Record. Then mode of delivery, uterotonic, blood loss, perineum, complications (APH, PPH, eclampsia, ruptured uterus, obstructed labour, sepsis), mother's condition, and the babies (weight, APGAR, outcome, essential newborn care). On submit, each live-born baby gets a Patient record linked to the mother.
- **PNC Visit**: visit number and MOH timing bucket (within 48 hours / 3 days to under 6 weeks / after).
- **Family Planning Visit**: method (pills, DMPA, condoms, implants, IUCDs, BTL, vasectomy, natural FP), insertion / reinsertion / removal for implants and IUCDs, New or Revisit (worked out from earlier visits for the same method), first-ever user, and timing (interval, immediate postpartum, postpartum, post abortion). Women-only and men-only methods are checked against the patient's sex.
- MOH 717 now counts ANC and PNC visits, deliveries by mode, births, stillbirths, neonatal deaths, low birth weight and maternal deaths.

**Maternity packages** (one price for a delivery instead of itemised charges):

- **Maternity Package**: delivery type (vaginal / caesarean section), billing item and price, insurer (SHA or another payor; blank = the cash package), included ward nights, and the items or item groups it includes. Enter SHA's current tariffs for the facility's level yourself - none are shipped.
- The **Delivery Record** picks the package for its delivery type and the admission's insurer, else the cash one; it can be changed, also after submitting.
- The **discharge bill** (the patient's first invoice dated on or after the delivery) gets the package line. Included charges stay on the bill at zero ("Included in ...") so the services are marked invoiced and the patient sees what the price covered; ward nights after the included ones are billed as usual. The package line references the Delivery Record, so it can't be billed twice.
- With an insurer, the package line gets a Patient Insurance Coverage from the insurer's eligibility for the package item (set one up on the plan, e.g. 100% for SHA), so the insurer's share goes to its receivable and onto the claim. Without an eligibility or an active policy the package is billed to the patient, with a message.
- eTIMS: register the package item like any other; KRA accepts the zero-priced included lines.

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

### Management dashboards

The **Kenya Health** workspace (sidebar: Kenya Health > Home) opens on the hospital's management dashboard. Each chart has Company and Period filters (Today, This Week, This Month, Last Month, This Quarter, This Year, Last 30 Days, Last 12 Months).

| Dashboard | Shows | Worked out from |
|---|---|---|
| Revenue by department | Net sales (before VAT, credit notes deducted) per department, split into the patients' and the insurers' share | What each invoice line was for: consultation, lab test, imaging, procedure, medicine, bed; hand-added charges while admitted count as Inpatient. An Item Group's *Revenue Department* overrides this |
| Bed occupancy | Occupied and vacant beds per ward now; daily occupancy % (midnight census); average occupancy over 30 days | Healthcare Service Units that take inpatient occupancy, and Marley's inpatient occupancy rows |
| SHA and insurance claims | Per payor: not yet claimed, awaiting payment, paid, rejected | Patient Insurance Coverage (invoiced, on no submitted claim) and Insurance Claims |
| Practitioner activity | Consultations, procedures and admissions per practitioner (top 15) | Submitted encounters, completed clinical procedures, inpatient records |
| Pharmacy stock | Medicines out of stock, below reorder level and expiring; stock value | **Pharmacy Stock Status** report: stock, reorder level, daily use over 30 days, days of cover, nearest batch expiry |

Kenya Health Settings sets the medicines item group (default Drug), the pharmacy warehouse (a group warehouse covers several stores), the expiry warning (90 days) and the minimum days of cover (14). Each card and chart needs read access to its records (Sales Invoice, Inpatient Record, Insurance Claim, Patient Encounter, Bin), so a nurse doesn't see revenue.

### Kitchen

- **Diet Type**: Normal, Soft, Diabetic, Nil by Mouth and so on; optional meal charge item per diet.
- **Diet Order** (per admission, submitted by a doctor or nurse): diet, from / until, meals per day, instructions; the patient's allergies come from the Patient. A new order ends the earlier open one on its start date; on a day two orders overlap, the later one counts.
- **Ward Diet List** report: what the kitchen cooks for a day - each admitted patient's ward, bed, diet, meals, instructions and allergies (in red), a count per diet, and patients with no diet order flagged.
- **Meal billing** (Kenya Health Settings): *Included in bed charge* (default, nothing added), *Per day* or *Per meal* (meals per day x days). An inpatient bill (an invoice with a ward line) gets a meal line per run of days on the same diet, up to discharge or the invoice date. Days on a submitted invoice are never charged again, so interim and final bills work, and cancelling a bill frees its days. Nil by mouth days are free. Meal items can be included in a maternity package.
- Role **Kitchen User**: reads diet orders and the ward diet list.

### Laundry

Linen are stock items (item group *Linen*), so ERPNext's stock balances say where every sheet is.

| Linen Movement | From | To |
|---|---|---|
| Issue to ward | Linen store | Ward linen store |
| Collect soiled from ward | Ward linen store | Laundry |
| Return clean to store | Laundry | Linen store |
| Condemn | Laundry (or linen store) | written off |
| Report lost | Ward linen store | written off |

Each submitted movement posts a Stock Entry (transfer, or issue for a write-off); cancelling it cancels the entry. Set the Linen Store and Laundry warehouses in Kenya Health Settings and a *Ward Linen Store* on each ward (group service unit). **Linen Status** report: each item in the store, the laundry and every ward, plus what was condemned or lost this month. Role **Laundry User** records movements (nurses can too).

### MOH reports

- **MOH 705 Outpatient Summary** (705A under 5 / 705B 5 and over): one row per indicator, days 1-31 and total. Rows are **MOH 705 Indicator** records, mapped to ICD-10/ICD-11 code prefixes, specific Diagnoses or lab tests, so the Health Records Officer can correct them. A diagnosis counts on its longest matching prefix; unmatched ones go to "All other diseases". New cases only (once per patient per indicator per month); first attendance = first outpatient day of the calendar year.
- **MOH 706 Laboratory Summary**: tests done, positives and low/high results per MOH 706 row, by month. Rows are **MOH 706 Indicator** records (149 seeded from KenyaEMR plus the malaria slide rows 3.1/3.2), each mapped by the lab to its own Lab Test Templates and, for compound tests, the result line (e.g. Glucose in Urinalysis); optional age group (under 5 / 5 and above). *Positive* rows count results containing one of the row's words and no negative word (negative, non-reactive, not seen, nil, absent...); *Numeric range* rows count results from the low value up to the high one, in the lab's units - confirm the seeded ranges for your analysers. Unmapped rows show "Not mapped to a lab test"; click a row to map it. Seeded rows are never overwritten.
- **MOH 711 Integrated Summary**: ANC/PMTCT, maternity and newborn, PNC and family planning from the maternity and FP records; first ANC visits and maternal deaths by the mother's age (10-14, 15-19, 20-24, 25+). Cervical cancer screening, child health and nutrition, SGBV, TB screening, psychiatry and physiotherapy are listed as "Not captured yet".
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

The demo pharmacy has reorder levels, so the dashboard shows amoxicillin below its level. Faith is discharged on the cash normal delivery package (demo price, not an SHA tariff). The demo lab's Hb and malaria slide tests are mapped to their MOH 706 rows. Daniel is nil by mouth on his theatre day, then on a soft diet (meals billed per day); the General Ward has linen issued, collected, returned and one sheet condemned.

The loader refuses to run unless the site opts in, so it can't touch a client's live data. It is safe to run again.

### License

MIT (scaffold default). Under review: Marley Health is GPL-3.0.

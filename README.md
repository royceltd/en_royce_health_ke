## RoyceERP Health (royce_health_ke)

The Kenyan layer for hospitals on [Marley Health](https://github.com/earthians/marley) (`healthcare`, branch `version-16`) and ERPNext v16. Registered with DHA AfyaConnect as **RoyceERP Health v1.0**.

It adds what a Kenyan hospital needs on top of Marley: SHA claims through DHA's Health Information Exchange, private insurance (Slade360 and insurers), maternity, theatre, MOH reports (705A/B, 717, 711, 710) and KHIS, and Kenyan identifiers and code sets. It works alongside the other RoyceERP apps when they are installed: `kenyan_accountant` (chart of accounts, VAT), `royce_etims` (KRA eTIMS), `royce_payments` (M-Pesa) and `royce_payroll_ke` (PAYE, SHIF, Housing Levy).

User guides with screenshots, for hospital staff: [docs/guides](docs/guides/README.md).

### Status

| Workstream | State |
|---|---|
| 0. Foundation: app, Marley fixes, demo loader | Done |
| 1. Kenyan identifiers and code sets (ICD-11/10, LOINC, PPB) | Done (ICD-10, LOINC, PPB lists to load from source files) |
| 2. SHA / HIE connector | Waiting for AfyaConnect sandbox approval |
| 3. Billing and private insurance | Done: bed nights, insured visits on Marley's model, claim rejections. Slade360 and separate insurer invoices pending |
| 4. Maternity | ANC, labour and delivery, newborn, PNC, family planning, maternity packages done (to align with the client's forms) |
| 5. Theatre | Booking, consent, theatre checklist (ward preparation, WHO, counts, post-op), anaesthesia record with the KSA pre-op assessment, operation note, and their prints, done |
| 6. Radiology | Worklist, perform/report/verify, accession numbers, MOH 717 imaging done; PACS/modality integration pending |
| 7. MOH reports, KHIS, dashboards | MOH 705A/B, 706, 711 and 717 done (mappings to confirm with the HRIO and lab); management dashboards done; KHIS submission pending. MOH 710 not needed by the first client |
| 8. Kitchen, laundry | Diet orders, ward diet list, meal charges; linen movements and status done |
| 9. Go-live readiness | Patient record access log, patient SMS, required registration details, masked patient details, triage vitals flags, the patient visit queue, the visit's running bill and payment before service done; two legal entities, SmartHealth import pending |

### Installation

```bash
bench get-app --branch version-16 https://github.com/earthians/marley
bench get-app royce_health_ke
bench --site <site> install-app erpnext healthcare royce_health_ke
```

Install the other RoyceERP apps first if the hospital uses them. A company must exist before `kenyan_accountant` and `royce_payroll_ke` can set it up: run their `provision(company)` after the setup wizard.

### Kenyan identifiers

- **Patient:** ID type and number (copied to Marley's unique UID, duplicates refused with the existing patient named), SHA member number, Client Registry ID (from the HIE), nationality, county, sub-county and residence, next of kin. **Residence** is a pick list (doctype Residence: estate, town or village, with county and sub-county, which fill in on the patient); reception adds new places from the field. The v0.22 patch turned residences typed before into list entries. Report **Patients by Residence**: patients registered and seen per place in a period (where patients come from, for marketing). Kenyan phone numbers are normalised to +254.
- **Required at registration** (Kenya Health Settings > Patient Registration, on by default): a new patient is refused until it has gender, date of birth, an ID or passport, a contact number, nationality and residence (county too for Kenyans). A child under 18 may have no ID and use the next of kin's phone. Exempt: emergency "unidentified patient" records (ER- series), data imports, and newborns registered from a delivery. An existing patient with gaps saves with a reminder.
- **Consultation (Patient Encounter):** shown as *Consultation* everywhere in English (`translations/en.csv`; the doctype keeps its name, so Marley updates and integrations are unaffected). Adds **Presenting Complaint** (chief complaint, history of presenting illness, review of systems, physical examination) and **Medical History**: the patient's allergies, current medication, past medical and surgical history, and family and social history (new Patient fields), fetched from the patient and editable; changes are written back to the Patient on save with a note naming the consultation (`history.py`). The Consultation Summary print shows them, allergies first.
- **Pricebooks (`schemes.py`):** Price Lists per payment category. Cash = the default selling list; each scheme (Eligibility Plan) names its list, shareable between schemes; the insurer contract's default list applies when the scheme's doesn't price an item (Marley's order). Added: a consultation on an insured Patient Visit takes the visit's policy (so its service requests are covered) and, on submit, gets cover for its fee as an insured appointment would; a consultation cover takes the scheme's price for the consultation item over the doctor's cash fee when the scheme's (or contract's) list prices it.
- **Theatre continuation sheet and post-op treatment sheet (v0.23, `postop.py`):** Theatre Booking › Continuation Notes (child Theatre Progress Note: time, stage, note, writer) added with **Add Progress Note**; saved notes can't be edited or removed (theatre.lock_progress_notes). Print *Continuation Sheet* (operation header from the operation note and anaesthesia record, procedure and findings, notes). **Treatment Sheet** (submittable, one per booking): regular drugs every N hours for N days, PRN drugs, once-only doses, dosage form from the drug's Medication; on submit it makes and submits the ward's Marley **Inpatient Medication Order** with every scheduled dose (PRN not scheduled); cancelling cancels the order unless the ward has handled a dose. Print *Treatment Sheet* in the paper layout with the X/D/V/S/R/OS administration grid.
- **Visits from appointments:** the visit's first consultation is linked to the visit's appointment, so the consultation fee is billed once (on the appointment; before v0.22 it was also billed on the consultation). An insured check-in gives an appointment booked without insurance the visit's cover.
- **Insured visits billed automatically** (`visit_bill.auto_bill`, Kenya Health Settings *Bill insured visits automatically*, default on): for an open insured visit, every refresh of the bill status (consultation submitted, lab test added, invoice or payment changed) adds the visit's unbilled charges to its single draft invoice (made with the first charge, inside a savepoint so a failure never stops clinical work); closing the visit adds the last charges and submits it (insurer's share to the claim, eTIMS signed, copay left outstanding). If submitting fails the visit still closes and the draft waits for the cashier.
- **Turnaround Time report (`tat.py`):** lab tests (order from the Service Request, sample collected, received = lab test created, result = `ke_result_at` stamped on submit, since Marley keeps only the submit date) and imaging (order, `ke_performed_at`, `ke_reported_at`). Summary per test type (count, median, average, 90th percentile, % within the template's *Target Turnaround (minutes)*) with a chart, or each request with its steps. A stated order time after the work began falls back to when the order was entered; out-of-order steps aren't counted.
- **Cashiers (`cashier.py`, Kenya Health Settings › Cashiers, both off by default):** *Only cashiers take payments* refuses patients' payments (Payment Entry with a patient's customer; payment on a POS invoice) for users without Cashier, Accounts Manager or System Manager, and hides the payment buttons for them; *Payments need an open cashier shift* requires the user's open **Cashier Shift** (opening float, optional own cash account that cash payments go to), tags each payment with it, and closing (submit) totals expected per mode of payment against the count, a difference needing a note. Role **Cashier** (v2 role defaults) gets billing access only. Payments posted as Administrator (M-Pesa callbacks) and insurers' payments are not affected.
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
- The **discharge bill** (the patient's first invoice on or after the delivery that bills ward nights of her delivery admission) gets the package line; her outpatient bills never do. Staff can add the package line by hand (referenced to the Delivery Record), and it is priced as the package. Included charges stay on the bill at zero ("Included in ...") so the services are marked invoiced and the patient sees what the price covered; ward nights after the included ones are billed as usual. The package line references the Delivery Record, so it can't be billed twice.
- With an insurer, the package line gets a Patient Insurance Coverage from the insurer's eligibility for the package item (set one up on the plan, e.g. 100% for SHA), so the insurer's share goes to its receivable and onto the claim. Without an eligibility or an active policy the package is billed to the patient, with a message.
- eTIMS: register the package item like any other; KRA accepts the zero-priced included lines.

Fields follow the MOH ANC, maternity and PNC registers (as in KenyaEMR) - align with the hospital's own forms.

### Theatre

Around Marley's Clinical Procedure (which carries the procedure's price and consumables):

- **Theatre Booking**: theatre (a service unit whose type is an OT), scheduled start and duration, surgeon, assistant, anaesthetist, priority, insurance pre-authorisation. Clashes on the theatre, surgeon, anaesthetist or patient are refused.
- **Surgical Consent** (submitted): what was explained, risks, alternatives, anaesthesia and transfusion consent, who consented, witness, scanned form.
- **Surgical Safety Checklist**, laid out like a hospital's paper theatre checklist (v0.18, from Bethesda's forms), one record per operation in tabs:
  - **Ward Preparation**: consent signed (from the booking), ID band, gown, shaving, jewellery/dentures/limb, fasting and last feed, IV line, catheter, NG tube, investigations (FHG, UEC, serology, X-ray, blood group, cross-match, units available), pre-op observations, pre-medication, and the handover: prepared by, handed over by, received in theatre by (times stamped). Done when the core items are answered.
  - **WHO Checklist**: Sign In, Time Out and Sign Out; each phase is Done when every item is answered, only after the one before, and time-stamped.
  - **Counts**: gauze and instrument lines (abdominal packs, gauze swabs, instrument set, blades, needles, add your own) with start, added, end. Sign Out can't confirm the counts unless every counted line balances (end = start + added) and the scrub and circulating nurses are named.
  - **Post-operative**: vitals, blood loss, level of consciousness, pain, oxygen, vomiting, catheter, dressing, drains, analgesia, infusion, drugs, recovery observations, investigations, remarks, and back to the ward (handed over by, received by, time). Only after Sign Out.
- **Anaesthesia Record** (submitted), in tabs:
  - **Pre-op Assessment** (as the GOK/KSA Anaesthesia Record): pre-op diagnosis, weight/height, smoking/alcohol/drugs, HR/BP/RR/SpO2, pallor, cyanosis, GCS (total worked out), a Yes/No review of 24 conditions across six systems, airway (loose teeth, dentures, abnormalities, Mallampati), current medication, steroid use, allergies (from the patient), Hb/Hct/platelets/WBC/PT/INR/APTT (filled from the patient's lab results in the last 30 days; **Fetch Lab Results** refreshes them), RFT/LFT/glucose/sickling, CXR/ECG/echo, ASA I-VI and E, pre-op orders.
  - **Anaesthesia** (the monitoring chart): technique, airway, E.T.T. size, position, pre-medication and time, induction and maintenance agents, start/end of anaesthesia and of surgery, drugs, intra-operative vitals, fluids and losses.
  - **Recovery**: Aldrete score, recovery discharge, post-operative instructions for the ward.
- **Operation note** on the Clinical Procedure: indication, incision, findings, procedure details, blood loss, specimens, implants, complications, post-op instructions.
- **Into Theatre** needs submitted consent, ward preparation done (an emergency may go in without it, with a warning), Sign In done and no pending/declined pre-authorisation (an emergency may proceed while pending); it creates and starts the Clinical Procedure. **Complete** needs Time Out, Sign Out and the operation note; it completes the procedure and issues its consumables from the theatre's warehouse.
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

### Printed documents

Hospital print formats in the same style as kenyan_accountant's Kenya Tax Invoice, so a patient's bill and their clinical papers look like one hospital's: hospital and facility (with MFL code) at the top, the document title in the accent colour, a patient band (name, patient number, age, sex, ID, SHA number, ward), clinician signature lines with cadre and registration number.

| Document | Print format | Default for |
|---|---|---|
| Lab Test | **Laboratory Report**: results with unit and reference range; a numeric result outside a numeric range is flagged H or L (text results are never guessed at); findings, organisms, sensitivities; performed by / verified by | Lab Test |
| Patient Encounter | **Consultation Summary**: vitals, allergies, chief complaint, complaints, history and examination, medical history, notes, diagnosis, investigations and procedures ordered, medicines | Patient Encounter |
| Patient Encounter | **Prescription**: the medicines slip for the pharmacy (no notes or diagnosis on it) | (Print › choose it) |
| Discharge Summary | **Patient Discharge Summary**: admission and discharge, length of stay, diagnosis, treatment, medicines to continue, advice, follow-up | Discharge Summary |
| Observation | **Radiology Report**: exam, modality, accession number, technique (radiographer, contrast, dose), findings, impression, reported/verified by; "Preliminary" until verified. Non-imaging observations print as an Observation Report | Observation |
| Clinical Procedure | **Operation Note**: with its Theatre Booking and Anaesthesia Record: team, anaesthesia type and agents, ASA, airway, indication, incision, findings, procedure, blood loss, specimens, complications, post-op instructions. Without a theatre booking: Procedure Note | Clinical Procedure |
| Surgical Consent | **Consent for Operation**: the hospital's wording ("I ... of P.O. Box ... hereby consent to Dr ... performing the operation of ... on myself / my child / my relative"), what was explained, consents ticked, signature lines for the patient or the person consenting, doctor and witness, and a thumbprint box. No Draft badge: it is printed to be signed, then scanned back | Surgical Consent |
| Surgical Safety Checklist | **Theatre Checklist**: 1 ward preparation and handover, 2 the WHO checklist, 3 the counts table, 4 the post-operative checklist. Unanswered items print as empty boxes and lines, so it also works as the paper form | Surgical Safety Checklist |
| Anaesthesia Record | **Anaesthesia Record**: the pre-operative assessment, then a page with the anaesthetic monitoring chart (vitals and drugs grids, X/S anaesthesia and surgery times), recovery and ward instructions | Anaesthesia Record |
| Patient | **Patient Card**: registration slip (details, next of kin, allergies, signatures) and a cut-out wallet card with the patient number and a QR of it | Patient |
| Diagnostic Report | **Diagnostic Results**: Marley's observation-based results (panels with components, H/L flags, text results) in the Laboratory Report layout | Diagnostic Report |

- With kenyan_accountant installed, the logo, address, accent colour (Kenya Accounting Settings › Printed Documents) and the client's own Letter Head rule are the same as on invoices.
- Defaults are set once (install, and patch `v0_16.set_hospital_print_formats` on existing sites), replacing only an empty default or Marley's own (Lab Test Print, Encounter Print, Diagnostic Report). A default the client picks afterwards is never touched (ADR-023). The formats are standard: fixes ship with the app; a client customises by duplicating one.
- Shared layout: `templates/print/health_document.html` (theatre forms add `templates/print/theatre_forms.html`: boxes and question/answer grids); data: `printing.py` (Jinja methods prefixed `health_`). The three theatre formats are the default through their own doctypes (`default_print_format`), no patch needed.

### Patient SMS

Needs the **Bulk SMS** app (royce_talk, RoyceTalk) on the site, enabled in Bulk SMS Settings. Without it the SMS buttons and jobs stay hidden or do nothing.

- **Consent**: Patient > **Agrees to Receive SMS** (`ke_sms_consent`, off by default; ask at registration). Campaigns, reminders and results messages only go to patients with it ticked, a mobile number and status Active.
- **One patient**: Patient > **SMS > Send SMS** opens a dialog with ready-made wording (please call us, results ready, missed appointment, medicine ready), a character and SMS count, and a warning if the patient hasn't agreed to SMS (staff can still send about their care). Logged in Bulk SMS Log against the patient; **SMS > SMS History** lists them.
- **Patient SMS Campaign** (Kenya Health > Patients): pick patients by facility visited, visit dates, department, sex, age, insurer (current policy) or active pregnancy. **Preview Recipients & Cost** counts them; Submit checks the RoyceTalk balance and sends through royce_talk's bulk sender in the background; the result (accepted, failed, cost, balance) is written back on the campaign.
- **Automatic** (Kenya Health Settings > Patient SMS): appointment reminders 2-24 hours ahead, once each, between 7am and 8pm (turns off Marley's own reminder, which ignores consent and addresses patients by their ID); "results ready" when a lab test is submitted. Wording is editable with `{{ first_name }}`, `{{ facility }}`, `{{ hospital }}`, `{{ phone }}` (reminders also `{{ date }}`, `{{ time }}`).
- Automatic messages never carry results or diagnoses. The facility comes from the service unit (Health Facility tree), its phone from the Health Facility, then the Company.

### Data protection: who opened which record

Every time a user opens or prints a patient's record - the Patient, encounters, vital signs, lab tests, observations, procedures, admissions, discharge summaries, medication and service requests, nursing records, and the maternity, theatre, diet and insurance claim records - a **Patient Record Access** entry is written: patient, record, view or print, user, IP address and time. Re-opening the same record within 10 minutes isn't logged again; every print is. Billing documents aren't tracked.

- Entries can't be edited or deleted and aren't removed by Frappe's log cleanup; deleting a patient or record keeps its trail.
- Healthcare Administrators and System Managers read the log (list view, filters by patient, user, record type and date; **View > Who Opened This Record** on a Patient).
- Written after the response is sent, so opening a record is never slowed; an audit failure is logged as an error and never stops a clinician.
- On by default (Kenya Health Settings > Data Protection). Not covered: lists and reports that show patient data without opening a record.

### Data protection: masked patient details

Patients' phone numbers, email, ID number and next of kin's phone are shown as XXXXXXXX to clinical, lab and pharmacy staff, and in full to **Receptionist** (new role), Healthcare Administrator and System Manager. The same goes for the copies on Inpatient Record and Lab Test. The Patient list shows only name, status and ID.

- Frappe's own field masking: it applies to lists, reports and forms. Server code (SMS, prints, claims) reads the real values, and a masked user saving a patient never overwrites them.
- Applied once per site (`privacy.apply_defaults`), then the hospital's to change: who sees what in Role Permissions Manager (the Mask column), which fields in Customize Form (Mask). Patient, Inpatient Record and Lab Test permissions become custom permissions when it runs.

### Patient visits and the queue

A **Patient Visit** is one arrival: reception checks the patient in, and the visit moves from station to station until it is completed.

- **Check-in** (from the Patient's *Create > Check In (New Visit)*, an appointment's *Start Visit*, or *+ Add*): visit type, service type, practitioner and department, referral, and payment. **Insurance** takes the payer, scheme, member number, relation to the principal member, limit, authorisation code and remarks. The patient's existing policy is picked up (or chosen); a new member's Patient Insurance Policy is created and submitted from what reception typed. Expired cover is refused. One open visit per patient per day. An appointment the patient came for is marked Checked In.
- **First station** from the visit type: outpatient and review go to Triage, casualty to Casualty, lab-, radiology- and pharmacy-only visits straight there.
- **The queue** is the Patient Visit list filtered by Station: each row shows the station and whether the patient is waiting or seen, minutes waiting (orange after 30, red after 60), payment method and the triage vitals flag. No phone or ID numbers.
- **Next consultant (v0.25, `assign.py`):** *Send To* Consultation with no doctor named (and no appointment) assigns a doctor on duty now: an active practitioner with a Practitioner Schedule slot for today covering this moment, the schedule row's service unit being the room (visit field *Room*, also on the movement). Only rooms inside the visit's **Facility** (Health Facility › its service unit group; the visit's facility is the user's default Health Facility, else the company's only one). Doctors of the visit's department first, else any doctor on duty with an orange message (a visit's department can be stale: it is fetched from the doctor named at check-in). Even share: fewest patients at Consultation now (waiting or in the room), then fewest sent today, then longest since their last patient. A file lock (`ke_next_consultant`) plus a commit serialises assignments. A doctor named by hand, or the appointment's, is kept (their room from the schedule). Nobody on duty: the sender is asked to choose. *Status › Reassign Doctor* gives a waiting patient to the next doctor on duty, keeping their place. The form shows *Consultation: doctor · room · service*; print **Queue Slip** (80 mm, the doctype's default format; *View › Queue Slip*) shows room, doctor, service and patients ahead. The list's **My Patients** shows the logged-in doctor's queue (Healthcare Practitioner › User). The demo has OPD Room 2 for Dr Brian (`masters.second_room`, tops up existing demos).
- **At a station:** *Seen* takes the patient off the waiting list; *Send To* moves them on (to Consultation with the practitioner), with an optional note. Every move is kept in Movements with who and when. *Record* opens Vital Signs or a Consultation for the visit; *Complete Visit* and *Cancel Visit* (with a reason) close it.
- **Links:** vital signs and consultations recorded that day link to the open visit. The visit shows the latest vitals flag; opening the consultation marks the patient seen at Consultation and fills its service type, practitioner and department from the visit.
- **Receptionist role:** registers patients, checks them in, records insurance policies and appointments; reads practitioners, departments, service types and payers. Added once per site (`roles.py`), then the hospital's to change.

### The visit's bill and payment before service

- **Running bill:** the visit form's Bill section lists everything given or ordered since check-in that is not invoiced yet (consultation, lab, imaging, procedures, drugs from the visit's consultations, bed), priced as the invoice will price it (insurance share included), then the visit's invoices with their balance, and Billed / Paid / To pay. The list's **Bill** pill reads To Bill, Unpaid or Paid, so the lab and pharmacy see at a glance whether a cash patient has paid.
- **Create Bill** (*Bill* menu, for anyone who can create a Sales Invoice) opens a draft invoice of the unbilled charges, linked to the visit; one draft at a time. Any patient invoice made that day links to the open visit.
- **Payment before service** (Kenya Health Settings > Payment Before Service, each on by default), for cash patients:
  - **Laboratory:** a lab test is started from its request only when the request is on a submitted, fully paid invoice. A test done without a request is not released (submitted) until it is paid.
  - **Radiology:** an imaging exam is marked performed only once paid.
  - **Pharmacy:** an invoice that issues stock (Update Stock) is submitted only when paid on the spot (Include Payment); a Delivery Note against a patient's invoice only once that invoice is paid.
  - **Exempt:** insured visits (and requests with an insurance policy), inpatients, casualty visits, and a visit where a manager (Healthcare Administrator, Accounts Manager) used *Allow Services Before Payment* with a reason, shown on the visit.
- **Uncovered insured items paid first (v0.24, `coverage.py`, Kenya Health Settings › *Insured: uncovered items paid first*; on for new sites and the demo, off on existing sites until switched on):** an insured visit is exempt only item by item. Covered = the item's Patient Insurance Coverage is Approved / Partly Invoiced / Invoiced (the scheme's Item Insurance Eligibility list). Anything else (not listed, rejected, or a manual-approval cover still in Draft) is paid first like a cash item. The insurer's automatic draft (`ke_bill_for` = Insurer) takes covered lines only; on an insured visit *Create Bill* makes the patient's bill (`ke_bill_for` = Patient) of the uncovered lines only; closing the visit submits the insurer's bill and leaves unpaid uncovered lines for the cashier. Copay on covered lines is still settled at close. The doctor gets a *Patient pays first* list on submitting the consultation; the visit's Bill section marks each line *Insurer's bill* or *Not covered* and shows *Patient pays now*, and *Send To* suggests the Cashier. Pharmacy: an insured invoice is exempt only when all its stock lines are covered.
- **Drug cover (v0.24):** Marley never covers drugs (Medication Request has no insurance fields). On submit, a Medication Request from an insured consultation gets a Patient Insurance Coverage from the scheme's eligibility for the drug item (`ke_insurance_coverage`); the visit bill carries it onto the invoice line like a covered service (covered quantity at the scheme price, any excess as a patient line).
- **Marley fix (v0.24, `coverage.CoverageEligibility` via extend_doctype_class):** Marley's `get_insurance_eligibility`, asked for an item with no template (a drug, a maternity package), also matched every template-less eligibility on the plan and returned the latest-starting one (a drug took the inpatient nursing fee's 100% manual cover). Our lookup matches the item's own eligibility, or the service template's. Worth reporting upstream.
- Marley's own *Process Service Request Only If Paid* only checks that a request is invoiced, not paid, and can't tell cash from insured: leave it off.
- Marley refuses to price a consultation whose practitioner has no OP consulting charge; the Bill section then says so. Set it on every consulting practitioner.

### Triage vitals flags

Each Vital Signs record is flagged **Normal** or **Abnormal** on save, with the abnormal readings listed (for example *Temperature 38.9 °C (high)*). Abnormal readings show in red on the form, and the Vitals column of the list is a red or green pill. Adds SpO2, which Marley lacks.

- Ranges (`vitals.py`, to confirm with the clinicians): temperature 35.5-37.5 °C, SpO2 94 % and over, pulse and respiratory rate by age band (under 1, 1-4, 5-12, 13 and over), BP from 13 years (systolic 90-139, diastolic 60-89), BMI for adults (18.5-24.9).
- The v0.19 patch flags vital signs recorded before.

### Marley fixes

Applied after install and every migrate, only where still broken (`royce_health_ke/setup/marley_fixes.py`):

- Patient History Settings ships Lab Test's comment field as a table, which crashes the submit of any lab test with a comment. The field types are re-read from the doctype.

### Demo

A fictional private hospital, **Kijani Valley Hospital Ltd**, and one patient's journey: registration, triage, consultation, cashier (M-Pesa), lab, admission, ward round, final bill with pharmacy dispensing, discharge. Receipts are signed with KRA eTIMS when the company has eTIMS active.

```bash
bench --site <demo-site> set-config royce_health_demo 1
bench --site <demo-site> execute royce_health_ke.demo.load
```

The demo pharmacy has reorder levels, so the dashboard shows amoxicillin below its level. Faith is discharged on the cash normal delivery package (demo price, not an SHA tariff). The demo lab's Hb and malaria slide tests are mapped to their MOH 706 rows. Daniel is nil by mouth on his theatre day, then on a soft diet (meals billed per day); the General Ward has linen issued, collected, returned and one sheet condemned. Daniel's appendicectomy has the full theatre paperwork: ward preparation and handover, balanced counts, the post-operative checklist and the KSA pre-op assessment (existing demo sites get it on the next `demo.load()`).

The loader refuses to run unless the site opts in, so it can't touch a client's live data. It is safe to run again.

### License

MIT (scaffold default). Under review: Marley Health is GPL-3.0.

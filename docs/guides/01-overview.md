# RoyceERP Health — Client Guide

RoyceERP Health runs a Kenyan private hospital from registration to the final bill in one system. Clinical records, billing, insurance, stock, accounts, KRA eTIMS and payroll share one database. It is built on ERPNext and Marley Health, with Kenya-specific modules from Royce Technologies Ltd.

This guide follows a live demo hospital, **Kijani Valley Hospital Ltd**. The hospital and all its patients are fictional, so you can click through freely.

## Overview

| Area | What it covers |
| --- | --- |
| Outpatient | Registration, check-in and station waiting lists, appointments, triage with vitals flags, consultation, lab and imaging orders, prescriptions |
| Inpatient | Admission, beds and wards, ward rounds, medication orders, discharge summary |
| Billing and cashier | A running bill on each visit, invoices from services ordered, payment before lab, radiology and pharmacy, M-Pesa and cash receipts, per-night bed charges, packages |
| Insurance | Policies, copay at the cashier, claims per visit, approvals, rejections and their settlement |
| Maternity | Pregnancy record, ANC visits, labour care guide, delivery, newborn, postnatal care, family planning |
| Theatre and radiology | Theatre booking, consent, WHO safety checklist, anaesthesia record; imaging worklist and reports |
| Reports | MOH 705A/B, 706, 711 and 717, management dashboards, patient record access log |
| Finance and compliance | Kenyan chart of accounts and VAT, KRA eTIMS invoice signing, payroll with PAYE, SHIF, Housing Levy and NSSF |

**Open the demo:** go to [hospital.royceltd.com](https://hospital.royceltd.com) and sign in with the login Royce sends you. Each user sees only the menus their role allows.

**Find your way around:**

- The narrow bar on the left is the **rail**. Click **Healthcare** on it to see the clinical areas: Healthcare, Outpatient, Inpatient, Emergency, Diagnostics, Rehabilitation, Insurance and Setup.
- **Kenya Health** sits on the same rail and holds the Kenyan modules: maternity, theatre, radiology, MOH reports, kitchen and laundry.
- The **search bar** at the top finds any patient, invoice or record by name or number.
- Every record links to the next step in its journey, for example from an encounter to its lab tests and invoice.

Step-by-step guides: [Reception, queue and billing](12-reception-queue-billing.md) · [Outpatient](02-outpatient.md) · [Inpatient](03-inpatient.md).

## Outpatient journey

An outpatient visit runs registration, triage, consultation, cashier and lab in one record, and the receipt is signed with KRA eTIMS. In the demo, follow **Grace Wanjiku Mwangi**, a walk-in patient with malaria, or **Lucy Wairimu Ndung'u** in the [Outpatient guide](02-outpatient.md).

1. **Registration (reception).** Create the Patient with ID type and number, contact number, nationality, county, residence and next of kin; these are required. Phone numbers are stored as +254, and a second patient with the same ID is refused, naming the existing record. Other staff see phone and ID numbers masked.
2. **Check-in (reception).** Open a **Patient Visit**: service type and doctor, cash or insurance (payer, member number, authorisation code). The patient joins the first waiting list, and every station sends them on with **Send To**. A booked Patient Appointment starts its visit with **Start Visit**.
3. **Triage (nurse).** Record Vital Signs: temperature, pulse, blood pressure, SpO2, weight and height. Readings out of range are flagged **Abnormal** in red, on the visit and the waiting list.
4. **Consultation (doctor).** Open a Patient Encounter. Record symptoms and diagnosis (ICD-11 codes are loaded), then order lab tests and prescribe drugs from the same screen.
5. **Cashier.** The visit's **Bill** shows what is not billed yet; **Create Bill** turns it into the Sales Invoice (or use *Get items from Healthcare Services*). Take payment by M-Pesa or cash.
6. **KRA eTIMS.** On submit, the invoice is sent to KRA and comes back signed with a KRA invoice number and QR code for the receipt.
7. **Lab.** Lab tests are created from the doctor's orders once paid (cash patients), results are entered and verified, and they appear in the patient's history. Radiology and the pharmacy also wait for payment; insured patients, inpatients and casualty are served first.

The full flow, with each station's waiting list and the visit's bill, is in the [Reception, queue and billing guide](12-reception-queue-billing.md).

**Practitioner records** hold the cadre, regulator (KMPDC, NCK, COC, PPB, KMLTTB), registration and licence numbers. Administrators are warned 30, 14, 7 and 1 day before a licence expires.

## Inpatient

An admission tracks the bed, ward rounds, medication and charges until discharge, and the final bill counts bed days per night. The full flow, with the ward drug chart and nurse dose records, is in the [Inpatient guide](03-inpatient.md).

1. **Admission order.** From the encounter, the doctor orders admission. The ward then admits the patient to a bed, for example General Ward Bed 01.
2. **Ward rounds.** Each round is a Patient Encounter on the inpatient record, with new orders as needed.
3. **Medication.** Inpatient prescriptions become a dose schedule. Drugs are issued from the pharmacy to the bed, and nurses record each dose given, by whom and when. A dose is billed when it is given.
4. **Kitchen and laundry.** Diet orders follow the patient (for example nil by mouth on theatre day), meals are billed per day, and linen issued to the ward is tracked.
5. **Discharge.** The doctor orders discharge and writes the discharge summary, the cashier raises the final bill, and the ward completes the discharge.

**Bed charges are per night:** one bed day for each midnight in the ward, at least one. A patient admitted at 13:00 and discharged next morning pays one night. A setting switches to per 24 hours if the hospital prefers.

## Insurance

For an insured patient, the cashier collects only the copay, the insurer's share goes to a claim, and rejected lines are settled rather than left on the insurer's account. In the demo, follow **Peter Otieno Kamau**.

1. **Policy.** Record the patient's insurance policy and the insurer's coverage terms.
2. **Coverage per service.** Services ordered under the policy get a coverage record, automatically or by manual pre-authorisation.
3. **Cashier.** The invoice shows the insurer's share on each line, and the patient pays the copay. One eTIMS invoice goes to the patient for the full amount.
4. **Claim.** An Insurance Claim per visit lists the covered lines. Mark each approved or rejected as the insurer responds, then record the insurer's payment.
5. **Rejected lines.** *Settle Rejected Lines* either bills the patient for the amount or writes it off to a Rejected Claims expense account. Cancelling the settlement reopens the line.

| Peter's visit | KES |
| --- | --- |
| Invoice total | 2,400 |
| Insurer's share claimed | 2,160 |
| Copay paid at the cashier | 240 |
| Approved and paid by the insurer | 1,800 |
| Rejected, billed to the patient | 360 |

SHA claims and Slade360 are not connected yet; see Status and roadmap.

## Maternity

Maternity follows the mother from booking to postnatal care, using the MOH registers and the MOH Modified WHO Labour Care Guide, and can bill a delivery as one package price. In the demo, follow **Faith Njeri Wambui**.

| Record | What it captures |
| --- | --- |
| Pregnancy Record | LMP and EDD (LMP + 280 days), gravida and parity, booking tests (blood group, Hb, HIV, syphilis, hepatitis B), risk factors |
| ANC Visit | Contact number and gestation worked out; examination, IPTp-SP, Td, iron and folate, ITN, danger signs |
| Delivery Record | Labour Care Guide observations with alerts flagged; mode of delivery, blood loss, complications, mother's condition, babies with weight and APGAR |
| PNC Visit | Visit number and MOH timing (within 48 hours, 3 days to under 6 weeks, after) |
| Family Planning Visit | Method, insertion or removal, new or revisit, timing after delivery |

**Labour Care Guide:** every value in the guide's ALERT column is flagged, as is slow cervical progress. The form is laid out like the paper guide, and *Print Labour Care Guide* prints it with alerts circled. Each live-born baby gets its own Patient record linked to the mother.

**Maternity packages:** a normal delivery or caesarean can be billed at one price. Charges it includes stay on the bill at zero, marked *Included in ...*, and extra ward nights are billed as usual. A package can be set per insurer, including SHA; the hospital enters its own tariffs.

Fields follow the MOH ANC, maternity and PNC registers. We will align them with your own forms during setup.

## Theatre and radiology

A patient cannot go into theatre without signed consent, the ward preparation and the WHO Sign In, and the swab count must balance before Sign Out. The forms follow the hospital's own paper theatre forms and print in the same layout. See the [Theatre guide](10-theatre.md).

**Theatre** (demo patient **Daniel Mutua Kioko**):

1. **Theatre Booking:** theatre, start time and duration, surgeon, assistant, anaesthetist, priority and insurance pre-authorisation. Clashes on the theatre, a surgeon, the anaesthetist or the patient are refused.
2. **Consent for Operation:** what was explained, risks, alternatives, anaesthesia and transfusion consent, witness; printed in the hospital's wording for signature or thumbprint, then the scan is attached.
3. **Surgical Safety Checklist**, one per operation:
   - ward preparation and handover to theatre
   - the WHO Sign In, Time Out and Sign Out, each time-stamped and done only after the one before
   - the swab and instrument count
   - the post-operative checklist back to the ward
4. **Into Theatre** needs:
   - submitted consent
   - ward preparation done; an emergency may go in without it, with a warning
   - Sign In done
   - no pending or declined pre-authorisation; an emergency may go in while it is pending
5. **Anaesthesia Record:**
   - the KSA pre-anaesthetic assessment: systems review, airway, GCS, ASA, and lab results filled in from the patient's tests
   - the monitoring chart: agents, drugs, vitals, fluids and losses
   - recovery and the post-operative instructions for the ward
6. **Complete** needs Time Out, Sign Out and the operation note (findings, incision, procedure). It then issues the consumables from the theatre store.

**Radiology** (demo patient **Joseph Kamau Njoroge**):

1. The doctor orders imaging from the encounter, like a lab test, and the exam gets an accession number.
2. The radiographer records the exam: contrast, dose, and the images attached or linked.
3. The radiologist writes findings and impression, then **Verify and Release** makes the report final.

The **Radiology Worklist** shows open exams, STAT and urgent first, with waiting time. Direct links to X-ray and ultrasound machines (DICOM/HL7) come once your equipment is known.

## Reports and dashboards

MOH reports come straight from the clinical records, management dashboards open on the Kenya Health home page, and every opening of a patient's record is logged.

| Report | What it shows |
| --- | --- |
| MOH 705A / 705B | Outpatient diseases for under 5 and 5 and over, per day of the month, from diagnoses mapped to ICD codes |
| MOH 706 | Laboratory tests done, positives and abnormal results per MOH row, by month |
| MOH 711 | ANC and PMTCT, maternity and newborn, PNC and family planning |
| MOH 717 | Outpatient attendances by clinic, sex and age; lab tests; admissions, discharges, deaths and referrals per ward; maternity and imaging |
| Theatre List, Radiology Worklist, Ward Diet List, Linen Status | Daily operating lists for theatre, imaging, kitchen and laundry |

The MOH mappings are a first pass from the KenyaEMR specification. Your Health Records Officer and lab will review them against the current MOH forms before go-live.

**Management dashboards** (Kenya Health › Home), each filtered by company and period: revenue by department, bed occupancy, SHA and insurance claims, practitioner activity, pharmacy stock. Each dashboard shows only what the user's role can read, so a nurse does not see revenue.

**Patient record access log (Data Protection Act):** each time a user opens or prints a patient's clinical record, the system writes who, which record, view or print, IP address and time. Entries cannot be edited or deleted. Administrators can see *Who Opened This Record* on any patient.

## Finance, KRA eTIMS and payroll

Every bill posts to a Kenyan chart of accounts, is signed with KRA eTIMS, and the hospital's payroll runs in the same system with current statutory deductions.

- **Accounts and VAT:** Kenyan chart of accounts and VAT set up when the hospital is created. Medical services are VAT exempt; taxable items carry 16% VAT on the same bill. Receivables are split by patient and by insurer. Stock (drugs, theatre supplies, linen) is valued in the same books, with reorder levels and batch expiry.
- **KRA eTIMS:** each invoice is sent to KRA on submit and returns a KRA invoice number and QR code, printed on the receipt. Items are registered with KRA, and stock received or issued is reported to KRA. Failed sends retry automatically every 15 minutes. A signed invoice is corrected with a credit note, which KRA also signs. The demo is connected to KRA's sandbox; go-live uses your own KRA PIN and device.
- **Payroll (Kenya):** salary structures for permanent staff and casual wages; PAYE, SHIF, Housing Levy and NSSF calculated on each payslip; payroll posts to the same accounts.

## Status and roadmap

The hospital workflows in this guide run end to end today; SHA claims through the HIE are the main piece still waiting, on DHA's sandbox approval. Until we are certified, keep SmartHealth and the SHA portal for SHA claims.

**Ready to use in the demo**

- Outpatient, inpatient (with ward drug chart and nurse dose records), cashier and per-night bed billing
- Private insurance: copay, claims, approvals, rejected-line settlement
- Maternity with packages and the Labour Care Guide, theatre, radiology, kitchen and laundry
- MOH 705A/B, 706, 711 and 717 reports, management dashboards, patient record access log
- KRA eTIMS signing (sandbox), Kenyan accounts and VAT, Kenyan payroll

**In progress or planned**

| Item | Where it stands |
| --- | --- |
| SHA claims through the HIE (AfyaConnect) | Waiting for DHA sandbox approval; then build, DHA testing and certification |
| Slade360 for private insurers | Waiting for API access |
| Separate eTIMS invoice to the insurer | Awaiting a tax adviser's view |
| Pharmacy dispensing queue | Planned: dispense at handover, partial dispensing, substitution, labels, controlled drugs register |
| KHIS submission of MOH reports | Planned; reports already run in the system |
| X-ray and ultrasound machine links (DICOM/HL7) | Once your equipment is known |

**Going live, in outline**

1. Confirm your forms, MOH mappings, price lists and insurer terms against the demo.
2. Set up your two legal entities and three facilities, each with its own KRA eTIMS device.
3. Import patients and opening balances from a SmartHealth export.
4. Train staff by role, then run alongside SmartHealth before switching over.

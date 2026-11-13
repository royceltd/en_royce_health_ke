# Bethesda Setup for Versions 0.24 and 0.25

Two changes reached bethesda.royceltd.com on 13 November 2026:

- **Version 0.24, insured patients pay first for what their scheme doesn't cover.** A test, exam or drug the scheme doesn't list is paid at the cashier before it is done. The insurer's bill carries only what the scheme covers.
- **Version 0.25, the next doctor is assigned automatically.** When triage sends a patient to Consultation, the system picks a doctor on duty in the patient's facility and gives the patient a slip with the room.

Neither works until the three setups below are done. Do them in this order. Each part ends with a check.

**Who:** Bethesda's system administrator (System Manager and Healthcare Administrator roles).

## What Bethesda has today

| | Now | Needed |
| --- | --- | --- |
| Facilities | Bethesda Main and Bethesda Kobujoi, each linked to its group of rooms | Nothing more |
| Consultation rooms | One per facility: *Main OPD Room 1*, *Kobujoi OPD Room 1* | One room per doctor seeing patients at the same time (Part 2) |
| Doctors | 3 practitioners, no schedules | A schedule with a room for every consulting doctor (Part 2) |
| Insurers and schemes | None | Each insurer, its schemes and each scheme's cover list (Part 1) |
| Staff facility | Not set | A default facility for every reception and triage user (Part 3) |

## Part 1: Load each scheme's cover list, then switch the rule on

The rule is simple: **if an item is not on the scheme's cover list, the patient pays for it first.** So the lists must be complete before the rule is switched on. A missing item sends insured patients to the cashier for something the insurer would have paid.

### 1.1 Insurers and schemes

**Where:** Insurance › Policies & Contracts.

1. **Insurance Payor:** one per insurer (SHA, each private insurer), with its customer and claims receivable account.
2. **Insurance Payor Contract:** the hospital's agreement with the insurer, with its start and end dates. Without an active contract nothing is covered.
3. **Eligibility Plan:** one per scheme the insurer sells (for example *SHA Primary Care*, *Corporate Gold*), with the scheme's **Price List** if it has its own tariff.

The [Insurance guide](../04-insurance.md), Step 1, explains each record.

### 1.2 The cover list

**Where:** Insurance › Policies & Contracts › **Item Insurance Eligibility**.

Each row says: *on this scheme, this item is covered at this percentage*. You need one row per scheme for every service and drug the scheme pays for: consultations, each lab test, each imaging exam, each procedure, each drug, ward days.

| Field | What to enter |
| --- | --- |
| Insurance Payor Eligibility Plan | The scheme |
| Eligibility For | **Item** |
| Item Code | The billing item: a lab test's or exam's item (on its template), a drug's item code, the consultation item |
| Coverage Percentage | What the insurer pays, for example 100, or 90 when the patient pays a 10% copay |
| Mode of Approval | **Automatic**, or **Manual** where the insurer requires pre-authorisation |
| Valid From | The date the scheme's cover started |

**Many rows at once:** use **Data Import** (search bar › *Data Import* › *+ Add*). Choose Document Type *Item Insurance Eligibility*, Import Type *Insert New Records*, download the template, fill one row per scheme and item in a spreadsheet, and upload it. Royce can prepare the file from each insurer's tariff list if you send it.

Good to know:

- **Manual approval:** the item is paid first until someone approves the cover (Insurance › Patient Insurance Coverage, set it to *Approved* and submit). Approve before the patient reaches the lab, or the patient is sent to the cashier.
- **Rows are per item.** There is no "whole item group" or "everything except" option yet. If an insurer covers everything except a short list, tell Royce: an exclusion option can be added.
- **Drugs** are now covered too, from the same list. Before version 0.24 the system never put drugs on the insurer's bill.

### 1.3 Switch the rule on

**Where:** Kenya Health › Kenya Health Settings › Payment Before Service.

1. Tick **Insured: uncovered items paid first**. It is off on Bethesda until you tick it.
2. Leave **Bill insured visits automatically** ticked. The two work together: the insurer's bill takes the covered items, and the cashier's **Create Bill** makes the patient's own bill of what isn't covered.
3. Save.

**Check:** check in an insured test patient, have a doctor order one covered and one uncovered test, and submit the consultation. The doctor sees *Patient pays first* listing the uncovered test. The visit's Bill section marks it *Not covered: patient pays first*, and the lab can start only the covered test.

## Part 2: Doctor schedules with rooms

The system treats a doctor as **on duty** when their schedule has a time slot covering the moment the patient is sent. The room on the schedule is the room printed on the patient's slip.

### 2.1 Consultation rooms

**Where:** Healthcare › Service Unit.

Add one room per doctor who consults at the same time, under the right facility: for example *Main OPD Room 2* with **Parent** *Bethesda Main - BHS*, type *Consultation Room*. A room in the wrong facility's group is never offered to that facility's patients.

### 2.2 Schedules

**Where:** Healthcare › Masters › **Practitioner Schedule** › *+ Add*.

1. Name the shift, for example *OPD Weekdays 08-17* or *Night 19-07*.
2. **Add Time Slots:** choose the days, the start and end time, and a slot length (15 minutes is fine; it only matters for booked appointments). A night shift past midnight (19:00 to 07:00) works.
3. Save. One schedule can be shared by many doctors.

### 2.3 Give each doctor their schedule and room

**Where:** Healthcare › Practitioner › open the doctor.

1. In **Practitioner Schedules**, add a row: the schedule and the **Service Unit** (their room). A doctor who works in different rooms on different days gets one row per schedule.
2. Check the **Department** (General Medicine, Paediatrics…). Patients whose visit has a department go to that department's doctors first.
3. Set **User** to the doctor's login, so **My Patients** on the Patient Visit list shows them their own queue.
4. Check the **OP consulting charge** is set, or the visit's bill can't price the consultation.

**Leave and days off:** remove the schedule row (or untick the day) while the doctor is away. A scheduled doctor who isn't in will still be sent patients. If that happens, triage opens each waiting patient and uses **Status › Reassign Doctor**.

**Check:** with two doctors on duty, send two test patients to Consultation with *Practitioner* left blank. Each goes to a different doctor, and **View › Queue Slip** shows the room.

## Part 3: A default facility for each user

Each visit records the **Facility** the patient checked in at. Doctors are assigned only from that facility's rooms, so a Main patient is never sent to a Kobujoi doctor. The visit takes the facility from the user who checks the patient in.

**Where:** search bar › **User Permission** › *+ Add*.

| Field | What to enter |
| --- | --- |
| User | The receptionist's or triage nurse's login |
| Allow | Health Facility |
| For Value | Bethesda Main, or Bethesda Kobujoi |
| Is Default | Ticked |
| Apply To All Document Types | Ticked: the user then sees only their facility's visits. Untick it for staff who work at both facilities |

Do this for every user who checks patients in or sends them to Consultation at triage. A visit checked in by someone without a default has no facility, and then doctors on duty at either facility can be assigned.

**Check:** log in as a Main receptionist and check a patient in. The visit's **Facility** reads *Bethesda Main*. Send the patient to Consultation: only Main doctors are picked.

## When something goes wrong

| What happens | Why, and what to do |
| --- | --- |
| *No doctor is on duty now … Choose the doctor.* | No schedule covers this moment in the patient's facility. Pick the doctor by hand in Send To, and fix the schedule (Part 2). |
| *No Paediatrics doctor is on duty now: sent to …* | The visit's department had nobody on duty, so another doctor on duty was picked. The visit's department comes from the doctor named at check-in: leave Practitioner blank at reception. |
| An insured patient is sent to the cashier for something the insurer pays | The item is missing from the scheme's cover list, or its cover waits for manual approval (Part 1.2). Add the row or approve the cover. A manager can also use **Bill › Allow Services Before Payment** on the visit. |
| Every insured patient is sent to the cashier | The rule was switched on before the cover lists were loaded. Untick it (Part 1.3) until they are. |

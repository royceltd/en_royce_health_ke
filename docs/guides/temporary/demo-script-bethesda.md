# Demo Script for Bethesda — Outpatient, Lab and Pharmacy

A 20-minute walk through Bethesda's own outpatient flow on the demo hospital, in the order of their requirements document (points 1 to 17). Each step says who logs in, what to click, and which of their points it answers. Everything on the demo is fictional.

**Where:** https://hospital.royceltd.com. The logins and the password are in *Demo logins.txt* (kept by Royce, not in this document). Use one browser window per login (or private windows), so you can switch roles without logging out.

**Before the demo:** ask Royce to refresh the demo that morning. Today's patients are then waiting at every stage. On each worklist, set **From** to today, so only today's demo patients show.

## 1. Reception: check-in, cash or insurance (points 1–2)

**Login:** reception. **Where:** Patient › *+ Add*, then **Create › Check In (New Visit)**.

- Register a patient. Point out the required details (ID, phone, nationality, residence) and that phone and ID numbers are masked for other staff.
- Check them in: service, **Cash or Insurance** (payer, scheme, member number), straight to Triage.
- Show the **Patient Visit** list: the waiting list per station.

## 2. Triage and the next doctor (points 2–3)

**Login:** nurse. **Where:** Vital Signs › *+ Add* for the patient (it links to today's visit), then on the Patient Visit **Send To › Consultation**.

- Record vitals. Abnormal readings turn red, and the visit shows *Abnormal*. No service is asked for again.
- **Send To Consultation without choosing a doctor:** the system picks the doctor on duty with the fewest patients, and shows doctor, room and service. Print the **Queue Slip** for the patient.

## 3. The doctor orders tests (point 4)

**Login:** amina.achieng (Dr Amina). **Where:** Patient Visit list › **My Patients**, open the consultation.

- Presenting complaint, history (saved back to the patient's file), lab tests and drugs.
- On submit: a cash patient goes to the Cashier first. For an insured patient, anything the scheme doesn't cover is paid first ("Patient pays first").

## 4. The laboratory (points 5–8)

**Login:** lab. **Where:** Kenya Health › Laboratory › **Lab Worklist**, *From* = today.

- **One row per patient, with the tests inside** (point 6): five patients today, each at a different stage.
- **Mercy:** three tests *Not paid*. They can't be collected until the Cashier is paid. Payment control at the lab.
- **Faith:** an **urgent walk-in** from an outside clinic (point 5). Show **Walk-in Request** to create one.
- **Samuel** (*Results Entry*): **Enter Results**, all three tests on one screen.
- **Esther** (*Validate Results*): Hb 9.1 shows **L**, white cells 13.4 shows **H** as you type. **Save and Validate** (point 7: validated by the person who entered).
- Print a Laboratory Report: who collected, who validated, when.

**Login:** Dr Amina. **Where:** Laboratory › **Results Inbox** (point 8).

- David's results are *New*. His Hb is **Abnormal** (12.9 is low for a man). Opening one marks it read.

## 5. The pharmacy (points 9–11)

**Login:** pharmacy. **Where:** Kenya Health › Pharmacy › **Pharmacy Worklist**, *From* = today.

- **Hassan:** prescription *Not billed*. **Bill Drugs** sends it to the Cashier (point 10: "pharmacy adds to billing").
- **David:** paid. **Dispense**: stock goes down and the **medicine labels** print, with the batch and expiry.
- **Agnes:** 10 of 15 capsules given, the rest waiting for stock (part dispensing).
- **Kevin:** one drug **sent back to the doctor** for a substitute (point 10), one **bought outside**.
- **Counter Sale** for a walk-in (point 11). Medicines are counted by the tablet, so a single tablet can be sold; strips and boxes are extra units of the same stock (set up as in the pharmacy setup guide).

## 6. The Cashier (points 12 and 16)

**Login:** cashier. **Where:** the Patient Visit › **Bill**.

- The visit's running bill, **Create Bill**, M-Pesa or cash, signed by KRA eTIMS.
- Cashier shifts: open, take payments, close and count (point 16).

## 7. Petty cash (point 17)

**Login:** reception, then accounts. **Where:** Kenya Accounting › Petty Cash › **Petty Cash Request**.

- Today's three requests: the receptionist's toner (*Pending Approval*), the night nurses' tea and sugar (*Approved*), the pharmacy's courier (*Paid*).
- As accounts: the float's balance on the list. Approve the toner (the accounts office approves, no limit, never your own request), **Pay**, and print the **Petty Cash Voucher** for signing. **Top Up Petty Cash** from M-Pesa.

## 8. Close: what else is ready

- Radiology worklist and reports (point 15), theatre forms, maternity, inpatient wards, MOH 705/706/711/717, management dashboards, SMS.
- On the roadmap, from their document: TB screening, claims and SHA, PACS for the Carestream X-ray and the Mindray ultrasound.

## If something goes wrong

- A list is empty: check the dates (*From* = today) and the pharmacy store (top of the Pharmacy Worklist).
- "Payment required": that is the payment rule working. Pay at the Cashier, or show a manager's **Allow Services Before Payment** on the visit.
- Anything else: a screenshot to Royce.

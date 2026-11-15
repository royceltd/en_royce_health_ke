# Bethesda Go-Live: 16 to 20 November 2026

The plan and checklist for moving Bethesda Main and Bethesda Kobujoi onto RoyceERP Health in the week of 16 November 2026. It follows the go-live proposal sent on 15 November: set up on Monday, parallel run Tuesday to Thursday, go/no-go and switch on Friday 20 November.

**Who:** Royce's go-live team, and Bethesda's go-live coordinator and department leads. Each task names who does it.

## Where we stand (15 November)

The pilot site, bethesda.royceltd.com, has the company, both facilities, the departments, stores per facility and one consultation room per facility. Almost everything the staff need from day one is still missing:

| | On the pilot now | Needed for the parallel run |
| --- | --- | --- |
| Staff logins | 1 (the administrator) | Every staff member, with roles |
| Doctors (Healthcare Practitioner) | 3, with no login, fee or schedule | Every doctor, linked to a login, with a consultation fee, a schedule and a room |
| Service prices | None | Consultations, procedures, imaging, bed charges, on the cash price list |
| Lab tests | None | Every test the lab runs, with price, sample and normal ranges |
| Medicines and stock | 1 medicine, no stock | The formulary, prices and opening stock per store |
| Insurers and schemes | None | Each insurer, scheme and its price list |
| Kenya Health Settings | Not saved | Pharmacy store, waiver account, walk-in lab doctor |
| Facility for each user | Not set | Every reception and triage user (decides which doctors they send to) |

So **the data, not the software, decides Friday.** The server move is about an hour's work for Royce. The lists below take Bethesda's staff most of Monday and Tuesday.

## What Bethesda sends by Monday noon

The proposal asked for the first three. The rest are needed just as much.

| # | What | Format | From |
| --- | --- | --- | --- |
| 1 | **Staff list**: name, work email or phone, job, facility (Main, Kobujoi or both) | Spreadsheet | HR / coordinator |
| 2 | **Cash price list**: every service (consultation types, procedures, imaging, nursing, bed per day) with its price | Spreadsheet, or SmartHealth's export | Accounts |
| 3 | **Each doctor's consultation fee**, and the days and hours they consult | Spreadsheet | Medical superintendent |
| 4 | **Lab test list**: name, price, sample type, result lines with unit and normal range | SmartHealth's test list export | Lab in-charge |
| 5 | **Medicines and consumables**: the five pharmacy upload templates (Royce sent them on 14 November) | Excel templates | Pharmacist in-charge |
| 6 | **Insurers and schemes** with their price lists, and for each scheme what it doesn't cover | Spreadsheet or the insurers' tariffs | Accounts / claims |
| 7 | Each facility's **MFL code and KEPH level** | Text | Administrator |
| 8 | Accounts to use: cash drawers, M-Pesa Paybill or Till, bank, petty cash float, patient waivers | Text | Accountant |

Royce loads 1 to 6 from the files (Data Import). Bethesda checks what was loaded (the checks in Part 2).

## The week

| Day | Royce | Bethesda |
| --- | --- | --- |
| **Mon 16** morning | DHA visit (certification). | Collect the lists above. |
| **Mon 16** day | Vilcom server: install, move the pilot site across, backups on (server runbook: `royce-erp-cloud/infrastructure/hospital/README.md`). | Send the lists by noon. |
| **Mon 16** evening | Load users, doctors, prices, lab tests, medicines, insurers. Check end to end with test patients. | Coordinator checks the loaded lists (Part 2 checks). |
| **Tue 17** | Logins handed out at both facilities. On site and on the phone. Second DHA visit if needed. | Parallel run starts: every patient in SmartHealth **and** RoyceERP Health. Pharmacy counts opening stock at close of day. |
| **Wed 18** | Opening stock loaded overnight. Fix issues (critical ones the same day). Evening progress report. | Parallel run. Daily comparison (Part 3). |
| **Thu 19** | Same. Agree the go/no-go list with management. | Parallel run. Department leads sign their part. |
| **Fri 20** | Go/no-go meeting. If go: SmartHealth becomes read-only for reference. | Management decides. All work in RoyceERP Health from then on. |
| **21 to 30** | Close support, daily check-in. | Report anything odd the same day. |

## Part 1: Before the parallel run (Monday)

Do these in order. Each later step uses the earlier ones. The guide named in each row has the screens.

| # | What | Where | Who | Guide |
| --- | --- | --- | --- | --- |
| 1 | Server ready, pilot site moved, backups running | Vilcom server | Royce | Server runbook |
| 2 | Staff users with their roles (table below) | Users › User | Royce, from list 1 | [Administrator setup](../08-administrator-setup.md), Step 1 |
| 3 | Default facility for each reception and triage user | User Permission (Health Facility, Is Default) | Royce | [Setup for 0.24 and 0.25](bethesda-setup-v0.25.md), Part 3 |
| 4 | Consultation rooms: one per doctor consulting at the same time | Healthcare › Service Unit | Royce, with the coordinator | Setup for 0.25, Part 2.1 |
| 5 | Doctors: login, department, licence, OP consulting charge, schedule with room | Healthcare › Practitioner | Royce, from list 3 | Setup for 0.25, Part 2 |
| 6 | Services and cash prices | Stock › Item, Item Price (Standard Selling) | Royce, from list 2 | Administrator setup, Step 3 |
| 7 | Lab tests | Healthcare › Lab Test Template | Royce, from list 4; lab in-charge checks | Administrator setup, Step 4 |
| 8 | Pharmacy: stores, units, medicines, prices, batches (not stock yet) | Data Import, files 1 to 5 | Royce, from list 5 | [Pharmacy setup and upload](../15-pharmacy-setup-and-upload.md), Steps 1 to 7 |
| 9 | Insurers, contracts, schemes, scheme price lists | Insurance › Policies & Contracts | Royce, from list 6 | [Insurance](../04-insurance.md), Step 1 |
| 10 | Mode of payment accounts: Cash, M-Pesa, Card, Bank | Accounts › Mode of Payment | Royce, with the accountant | [Cashier day-end](../07-cashier-day-end.md) |
| 11 | Patient Waivers expense account; Petty Cash account and float | Accounts › Chart of Accounts | Accountant | [Petty cash](../16-petty-cash.md) |
| 12 | Kenya Health Settings (values below), then **Save** | Kenya Health › Kenya Health Settings | Royce | Administrator setup, Step 6 |
| 13 | Test patients end to end at each facility (Part 2) | | Royce, then the coordinator | This guide |
| 14 | Delete the test patients and their bills, or cancel them | | Royce | |

**Roles for each job** (from guide 08):

| Job | Roles |
| --- | --- |
| Reception | Receptionist |
| Triage nurse, ward nurse, midwife | Nursing User |
| Doctor, clinical officer | Physician (and the login set as **User** on their practitioner record) |
| Lab | Laboratory User |
| Pharmacy | Pharmacist, Stock User |
| Cashier | Cashier |
| Accounts office | Accounts User (petty cash, payments) |
| Manager approving discounts, waivers, pay-later | Healthcare Administrator or Accounts Manager |
| Administrator | System Manager, Healthcare Administrator |

**Kenya Health Settings for Bethesda:**

| Setting | Value |
| --- | --- |
| Pharmacy: medicines item group | Drug |
| Pharmacy warehouse | Bethesda Main's Pharmacy store (the default: Kobujoi's pharmacist picks Kobujoi's store on the Pharmacy Worklist) |
| Payment before service: lab, radiology, pharmacy | On |
| Bill insured visits automatically | On |
| Insured: uncovered items paid first | **Off** until each scheme's cover list is loaded |
| Payment: waiver account | Patient Waivers (step 11) |
| Laboratory: requesting doctor for walk-ins | The lab's medical officer in charge |
| Laboratory: a second person validates results | Off (Bethesda: whoever enters results validates them) |
| Only cashiers take payments | On |
| Payments need an open cashier shift | On |
| Require full registration details, patient record access log | On |

## Part 2: The end-to-end check (Monday evening)

At each facility, with test patients, logged in as each role (not as the administrator):

| # | Journey | Expected |
| --- | --- | --- |
| 1 | Reception registers a cash patient and checks them in for a general consultation | The visit shows the facility; the patient is on the triage list |
| 2 | Triage records vitals and sends to Consultation, doctor left blank | A doctor on duty is picked, and the queue slip shows the room |
| 3 | The doctor orders one lab test and one medicine | The patient is sent to the cashier first (cash patient) |
| 4 | Cashier opens a shift, takes payment for the consultation, test and medicine, and prints the receipt | Receipt correct; the lab and pharmacy worklists show *Paid* |
| 5 | Lab collects the sample, enters and validates the result | The result reaches the doctor's Results Inbox |
| 6 | Pharmacy dispenses from the pharmacy store | Stock goes down; the label prints |
| 7 | An insured patient: check in with a policy, consultation, a test | No payment asked; the bill goes on the insurer's invoice |
| 8 | A discount asked at the cashier | The manager approves it from Patient Bills › Approvals waiting; the bill shows the discount |
| 9 | Cashier closes the shift | Takings by mode match what was entered |
| 10 | A petty cash request, approved and paid | The petty cash account goes down |

Any line that fails is fixed before Tuesday morning, or written down with a workaround the staff are told about.

## Part 3: The parallel run (Tuesday to Thursday)

**Every patient goes into both systems.** SmartHealth stays the hospital's working record until Friday. Where the two disagree, SmartHealth is right and RoyceERP Health gets fixed.

**At the end of each day** the coordinator and Royce compare:

| What | RoyceERP Health | Should equal |
| --- | --- | --- |
| Patients seen, per facility | Patient Visit list, today, by Facility | SmartHealth's daily visits |
| Lab tests done | Lab Worklist, today's validated tests | SmartHealth's lab register |
| Bills and amounts | Patient Bills, today | SmartHealth's billing summary |
| Cash, M-Pesa and card collected, per cashier | Closed Cashier Shifts, today | SmartHealth's collections, and the cash counted |
| Drugs dispensed | Pharmacy Worklist, *Dispensed* tab, today | SmartHealth's dispensing list |

Royce sends a short report each evening: what was raised, what was fixed, what is still open, and whether Friday still looks right.

**Opening stock:** the pharmacy counts every store by batch after the last sale on Tuesday evening. Royce loads the count overnight ([Pharmacy setup](../15-pharmacy-setup-and-upload.md), Step 8). From Wednesday the pharmacy's stock in RoyceERP Health is real.

**Opening balances** (amounts insurers and patients owe from SmartHealth): one total per insurer as of the switch date, entered by the accountant. Old claims are followed up in SmartHealth until they are paid.

## Part 4: Friday's go/no-go

Go if **all** of these are true. Each lead ticks their own line.

| # | Criterion | Signed by |
| --- | --- | --- |
| 1 | Reception: every patient checked in on Wednesday and Thursday is in both systems, with the right facility and payer | Reception lead |
| 2 | Clinicians: consultations, orders, prescriptions and results work for real patients | Medical superintendent |
| 3 | Lab: every test done is on the Lab Worklist with its result | Lab in-charge |
| 4 | Pharmacy: stock matches the count; dispensing takes the right batch and price | Pharmacist in-charge |
| 5 | Cashiers: Thursday's collections match SmartHealth, per mode and per cashier | Accounts lead |
| 6 | No critical issue open (a patient can't be served, billed or paid) | Coordinator, Royce |
| 7 | Backups are running, and a restore was tested | Royce |

**No-go:** staff continue in SmartHealth, and the parallel run continues on Monday 23 November. Ten days remain before the DHA deadline.

**After go:** SmartHealth is used only to look things up. Nothing new goes into it.

## Day one for each role

| Role | Morning | Through the day | End of day |
| --- | --- | --- | --- |
| Reception | Log in; open the Patient Visit list (your facility) | Register, check in (cash or insurance), send to triage | Visits still open: send on or complete |
| Triage | Patient Visit list, *Triage* | Vitals, then **Send To › Consultation** (doctor picked automatically) | Nobody waiting at triage |
| Doctor | Patient Visit list, **My Patients**; Results Inbox | Consult, order, prescribe; read results as they come in | Results Inbox read; visits completed |
| Lab | Lab Worklist (From = today) | Collect, enter results, validate; walk-in requests | Nothing left uncollected or unvalidated |
| Pharmacy | Pharmacy Worklist (From = today) | Bill drugs for the cashier, dispense when paid, counter sales | Returns done; worklist clear |
| Cashier | **Open your Cashier Shift** with the float | Create Bill on the visit, take payment, print the receipt; ask a manager for discounts and waivers | **Close the shift**: count, enter, explain any difference |
| Manager | Patient Bills › Approvals waiting | Decide discounts, waivers, pay-later | Unpaid bills on Patient Bills reviewed |
| Accounts | Petty Cash Requests | Approve and pay petty cash; check receipts by mode | Day-end checks ([Cashier day-end](../07-cashier-day-end.md)) |

**When something goes wrong:** write down the patient, the screen and what you pressed, take a screenshot, and call or WhatsApp Royce's go-live line. In the parallel run, carry on in SmartHealth and catch up in RoyceERP Health once it's fixed.

## Risks and what we do about them

| Risk | What we do |
| --- | --- |
| **Internet down at a facility.** The system runs on a server in Nairobi, so a facility without internet can't use it. | Each facility needs a second connection (a different provider, or a 4G router with data) before Friday. In an outage, record on paper and enter the records once the connection is back. |
| Lists arrive late or incomplete | Load what has arrived. A service without a price can't be billed, so the cashier uses an agreed *Miscellaneous* item until it is priced. |
| An insured patient sent to pay for something the insurer covers | Covered-items checking stays off until cover lists are loaded (Part 1). Until then, insured visits are billed in full to the insurer. |
| Doctor auto-assignment sends patients to someone absent | Keep schedules current. Triage can **Reassign Doctor**. |
| DHA certificate not issued by Friday | Royce returns to DHA daily. It doesn't block the parallel run. |
| Something critical breaks after Friday | Daily backups plus hourly database copies. Royce restores to the last hour at most, and staff go back to paper for that gap. |

## Not in this go-live

- **SHA claims and the claims workbench:** claims are prepared as today until the claims workbench is ready (after go-live).
- **KRA eTIMS invoices:** off at go-live unless Bethesda's accountant says the hospital must issue eTIMS invoices from day one. Decide by Wednesday, because the opening stock must then be registered with KRA.
- **TB screening card, MOH 705/711 extras, PACS:** after Bethesda's answers.

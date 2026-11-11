# Reception, Queue and Billing — Testing Guide

A short script to test registration, check-in, the waiting lists, the vitals flags, the visit's bill and payment before service, before using them with real patients. Each test says what to do and what the system should do. Tick each one off. If anything behaves differently, send a screenshot.

Test on the demo hospital (hospital.royceltd.com), not on your live site, because the tests create patients, visits and invoices. The steps are explained in full in the [Reception, queue and billing guide](12-reception-queue-billing.md).

## Before you start

You need three logins (Royce can create them for you on the demo):

| Login | Roles | Used for |
| --- | --- | --- |
| Reception | Receptionist | Registration and check-in |
| Nurse | Nursing User | Triage, and seeing masked details |
| Manager | Healthcare Administrator, Accounts User, Laboratory User | Cashier, lab and approving services before payment |

Use the doctor **Dr Amina Achieng** and the service type **General Consultation**. Write down the visit numbers you create (VIS-…).

## A. Registration

Log in as **Reception**. Healthcare › Patient › *+ Add Patient*.

| # | Do this | The system should |
| --- | --- | --- |
| 1 | Enter a first and last name, sex and date of birth (an adult) only. Save. | Refuse, listing what is missing: ID, mobile number, county and residence (nationality starts as Kenya). |
| 2 | Add ID type *National ID* and a number, a mobile number and nationality **Kenya**. In Residence type a new place, choose **Create a new Residence**, leave its county blank and save it. Save the patient. | Refuse: the county is needed for a Kenyan. Choose a county and save. |
| 2a | On another new patient choose county **Nakuru**, then open the Residence list. Pick a Nakuru place. | The list shows Nakuru's places (and places with no county); the sub-county fills in. |
| 2b | Reports › **Patients by Residence**, this month. | Each place with the patients registered and seen, busiest first, and a chart. |
| 3 | Register a child of 5 with ID type **None**, no mobile, and the next of kin's phone. | Save it. |
| 4 | Register an adult with ID type **None**. | Refuse: *None* is only for children. |
| 5 | Enter the ID number of the patient from test 2 on a new patient. | Refuse, naming the existing patient. |

## B. Masked details

| # | Do this | The system should |
| --- | --- | --- |
| 6 | As **Nurse**, open the Patient list, then the patient from test 2. | The list shows no phone or ID. On the form, the mobile and ID number show as XXXXXXXX. |
| 7 | As **Nurse**, change the patient's blood group and save. As **Reception**, open the patient. | Reception sees the real mobile and ID number, unchanged. |

## C. Check-in and the waiting lists

As **Reception**:

| # | Do this | The system should |
| --- | --- | --- |
| 8 | On the patient from test 2, **Create › Check In (New Visit)**. Visit type *Outpatient*, General Consultation, Dr Amina, Cash. Save. | Save the visit at **Triage: waiting**, with the age worked out and one line under Movements (Reception → Triage). |
| 9 | Check the same patient in again. | Refuse with **Already checked in**, naming the visit from test 8. |
| 10 | Check in a different patient as *Lab only*. | It goes straight to **Laboratory: waiting**. |
| 11 | Open Kenya Health › Patient Visit and set **Station** to Triage. | Show the visit from test 8 with its minutes waiting. After 30 minutes the time turns orange. |
| 12 | Check in *Peter Otieno Kamau* with **Insurance**, payer *Mlima Health Assurance (Demo)*. | His policy fills in by itself, with the member number. |
| 13 | Check in another patient with **Insurance**, a new member number and **Cover Valid Until** yesterday. | Refuse: the cover has expired. Change the date to next year and save: a Patient Insurance Policy is created for the patient. |

## D. Triage and consultation

As **Nurse**, on the visit from test 8:

| # | Do this | The system should |
| --- | --- | --- |
| 14 | Press **Seen**. | The status turns **Triage: seen** and the movement gets the time seen. |
| 15 | **Record › Vital Signs**: temperature 38.9, pulse 110, SpO2 91, BP 120/80. Save. | Flag it **Abnormal**, with the temperature, pulse and SpO2 in red and listed at the top. The visit shows Vitals **Abnormal**, and so does the waiting list. |
| 16 | Record vital signs for another adult: temperature 36.8, pulse 80, SpO2 98, BP 118/76. | Flag them **Normal**. |
| 17 | On the visit, **Send To** Consultation, Dr Amina. | The visit moves to **Consultation: waiting**, with a second movement line. |
| 18 | As **Manager** (or a doctor), **Record › Consultation**. Order a **Malaria Blood Slide**. Save and submit. | The consultation opens with Dr Amina and General Consultation filled in. The visit turns **Consultation: seen**. |

## E. The bill

| # | Do this | The system should |
| --- | --- | --- |
| 19 | Open the visit from test 8. | The **Bill** section lists the consultation (1,500) and the malaria slide (500) under *Not billed yet*, To pay 2,000. Bill status **To Bill**, and the same in the waiting list. |
| 20 | As **Manager**, start the lab test: open the malaria slide's **Service Request** and create the lab test. | Refuse: **Payment required** … *Send the patient to the Cashier*. |
| 21 | On the visit, **Bill › Create Bill**. Save the invoice and submit it. Don't take payment. | The invoice shows the two lines and the visit number. The visit turns **Unpaid**. |
| 22 | Try test 20 again. | Still refused: billed is not paid. |
| 23 | On the invoice, **Create › Payment** for the full amount and submit. | The visit turns **Paid**: the invoice shows with balance 0, To pay 0. |
| 24 | Try test 20 again. | The lab test is created. |
| 25 | Open the **Bill** menu on the visit. | **Create Bill** is no longer offered: nothing is waiting to be billed. |

## F. Exemptions and approval

| # | Do this | The system should |
| --- | --- | --- |
| 26 | On Peter's insured visit (test 12), have the doctor order a malaria slide, then start the lab test without billing. | Let it start: insured patients are served first. |
| 27 | Check in a new cash patient, order a test, then as **Manager** use **Bill › Allow Services Before Payment** with the reason *Staff, pays at month end*. Start the lab test. | The reason shows at the top of the visit. The lab test starts unpaid. |
| 28 | As **Reception**, open the same visit. | No *Allow Services Before Payment* option: only managers have it. |
| 28a | As **Administrator**, make a price list *SHA-PHC (test)* (Selling) with General Consultation at 500, and set it as the **Price List** of the plan *Corporate Gold (Demo)*. Check in a new patient on that insurer and plan, consult and submit the consultation. Open the visit's **Bill**. | The consultation is 500, not the doctor's 1,500, and the insurer's share shows. The consultation carries the visit's policy, and its coverage is under Insurance › Coverage. Put the plan's price list back afterwards. |

| 28g | Check in a new patient on the demo insurer (plan Corporate Gold), consult and order a malaria slide, submit. Open the visit's **Bill**. | Without pressing Create Bill, the visit has a draft invoice with the consultation and the test, each with the insurer's share. |
| 28h | Order another test in a review consultation. | The same draft invoice gains the new lines; there is still one invoice. |
| 28i | **Close** the visit. | The invoice is submitted (signed by KRA), the insurer's share is on it and the copay is what the patient owes. |

## F2. Cashiers and shifts

As **Administrator**, in Kenya Health Settings › Cashiers tick both switches. Give a test user only the **Cashier** role.

| # | Do this | The system should |
| --- | --- | --- |
| 28b | As **Lab**, open an unpaid patient invoice. | No **Create › Payment** and no *Include Payment*. |
| 28c | As the **Cashier**, take a payment on it before opening a shift. | Refuse: *Open your cashier shift first*. |
| 28d | Kenya Health › Cashier Shift › *+ Add*, float 1,000, save. Take the payment in cash. | The payment shows the shift. |
| 28e | Open the shift, **Refresh Takings**. Enter Counted 50 less than Expected for cash. **Close Shift**. | Expected = float + the payment. The difference is −50 and closing asks for a note; with a note it closes as **Closed**. |
| 28f | Switch both settings off again (or leave them on if the hospital wants them). | |

## G. Pharmacy

| # | Do this | The system should |
| --- | --- | --- |
| 29 | For a cash patient's visit, make a Sales Invoice with paracetamol, **Update Stock** ticked and the pharmacy store. Submit without **Include Payment**. | Refuse: *Drugs leave the store only when paid.* |
| 30 | Tick **Include Payment**, enter the payment for the full amount, and submit. | Submit it; the stock goes down. |
| 31 | Make a second invoice without Update Stock, submit it unpaid, then **Create › Delivery Note** and submit. | Refuse the Delivery Note: the invoice is unpaid. Pay the invoice and submit the Delivery Note again: it goes through. |

## H. Closing

| # | Do this | The system should |
| --- | --- | --- |
| 32 | On the visit from test 8, **Status › Complete Visit**. | The visit turns **Completed** and leaves the waiting lists. **Send To** is no longer offered. |
| 33 | Cancel the visit from test 10 with a reason. | It turns **Cancelled**, with the reason shown. |

## Tell us

1. Any test where the system did something different, with a screenshot.
2. **Vitals limits:** are these right for your hospital? Fever above 37.5 °C, SpO2 below 94 %, blood pressure 90–139 / 60–89 from 13 years, pulse and breathing rate by age band (the full table is in the guide).
3. **Payment before service:** should any department or patient group also be served first (for example antenatal mothers, or staff)?
4. **Stations:** are Triage, Consultation, Casualty, Laboratory, Radiology, Pharmacy, Procedure Room, Cashier and Admission the right list? What do you call yours?
5. Which details may nurses and doctors see in full (for example the phone number, to call a patient back)?

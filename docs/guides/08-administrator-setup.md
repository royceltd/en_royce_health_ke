# Administrator Setup — Step-by-Step Guide

What the hospital's system administrator sets up in RoyceERP Health before staff start work, and keeps up to date afterwards. Shown on the demo hospital at hospital.royceltd.com.

## At a glance

Set these up in this order before staff start; each later step uses the ones before it.

| # | What | Where | Done by |
| --- | --- | --- | --- |
| 1 | Staff users and roles | Users › User | Administrator |
| 2 | Practitioners and licences | Healthcare › Practitioner | Administrator, HR |
| 3 | Services and prices | Stock › Item, Item Price | Finance |
| 4 | Lab tests, medicines, dosages | Healthcare › Setup | Lab manager, pharmacist |
| 5 | Wards, beds and their stores | Healthcare › Service Unit | Administrator |
| 6 | Hospital-wide settings | Healthcare Settings, Kenya Health Settings | Administrator |

The company, chart of accounts, VAT, KRA eTIMS and payroll are set up by Royce during installation.

## Step 1 — Staff users and roles

**Where:** Users › User › *+ Add User*.

1. Enter the staff member's work email, first and last name. Untick *Send Welcome Email* if you will hand over the login yourself.
2. On **Roles & Permissions**, tick only the roles the job needs:

| Job | Roles |
| --- | --- |
| Reception | Receptionist (registers and checks in patients, records insurance policies, sees phone and ID numbers) |
| Doctor | Physician |
| Nurse, midwife | Nursing User |
| Lab technologist | Laboratory User; LabTest Approver to verify results |
| Pharmacist | Stock User |
| Cashier | Cashier (takes patients' payments, opens and closes their own shift; add Accounts User only if they also do accounts work) |
| Manager who approves services before payment | Healthcare Administrator or Accounts Manager |
| Kitchen, laundry | Kitchen User, Laundry User |
| Hospital administrator | Healthcare Administrator |

3. Save, then set a password under **Password** or let the welcome email do it.
4. When someone leaves, untick **Enabled**; never delete a user, so their records keep their name.

Roles decide what each person sees: a nurse does not see revenue, only administrators read the patient record access log, and only Receptionist, Healthcare Administrator and System Manager see patients' phone and ID numbers (others see XXXXXXXX). Who sees them can be changed in Role Permissions Manager (the Mask column).

Each cashier needs their own login: payments and shifts are recorded under the person who took them. In **Kenya Health Settings › Cashiers**, *Only cashiers take payments* stops other service points (lab, pharmacy, wards) from receiving money: they can bill, but only users with the Cashier, Accounts Manager or System Manager role can record a payment. *Payments need an open cashier shift* makes each cashier open a shift first (see the [Cashier Day-End guide](07-cashier-day-end.md)). Both are off until you switch them on.

Demo users: *amina.achieng@kijanivalley.example* (Physician) and *nurse.wanjiru@kijanivalley.example* (Nursing User), both fictional.

![User record](images/admin/01-user.png)

*A staff user; roles are on the Roles & Permissions tab.*

## Step 2 — Practitioners and their licences

**Where:** Healthcare › Practitioner › *+ Add*.

1. Enter the name, department and **User** (the login from Step 1), so encounters and orders carry the right doctor.
2. In the registration section, enter the **cadre**, **regulator** (KMPDC, NCK, COC, PPB, KMLTTB), registration number, practising licence number and **licence expiry**.
3. Under **Charges**, set the **OP consulting charge item** and fee for every doctor who sees outpatients. Without it the consultation can't be priced, and the visit's bill says so.
4. Add a **Practitioner Schedule** for the days and times they see patients, with their **room** (service unit) on each schedule row. This books appointments, and it decides who is **on duty**: patients sent to Consultation without a doctor are shared out among the doctors whose schedule covers that moment, and sent to the room on the schedule. Keep schedules current; a doctor on leave should have the schedule row removed or the schedule disabled for that time.
5. With more than one facility in a company (Bethesda Main and Kobujoi), give each **Health Facility** its service unit group, and give each reception and triage user a default facility: **User Permission** on *Health Facility* with **Is Default** ticked. Each visit then takes that facility, and only doctors with rooms in it are assigned.

Healthcare Administrators are notified 30, 14, 7 and 1 day before a licence expires, then weekly once it has expired.

Demo record: Dr Amina Achieng, Medical Officer, KMPDC, licence expiring 26 May 2027 (demo numbers).

![Practitioner registration and user](images/admin/02-practitioner.png)

*The practitioner's cadre, regulator, licence and expiry, linked to their login.*

## Step 3 — Services and prices

**Where:** Stock › Item (each billable service) and Stock › Item Price.

1. Each service the hospital charges for is an **Item**: consultations, lab tests, imaging, procedures, bed per night, nursing, meals. Services are non-stock items; medicines and consumables are stock items.
2. Give each item its **Item Tax Template**: medical services are VAT exempt; taxable goods carry 16%. The KRA eTIMS tab fills in from it.
3. Set the price in **Item Price** on the *Standard Selling* price list (the cash price). Each insurance scheme with its own tariff gets its own price list, which several schemes can share: see *Pricebooks* in the [Insurance guide](04-insurance.md), Step 1.
4. Register new items with KRA eTIMS before they are first sold (the item's KRA eTIMS tab, or the Compliance Status report).

Demo prices: general consultation KES 1,500, haemoglobin KES 400, general ward bed KES 4,500 per night.

![Item prices](images/admin/03-item-price.png)

*Item Price on the Standard Selling price list.*

## Step 4 — Lab tests, medicines and dosages

**Lab Test Template** (Healthcare › Setup): one per test the lab runs — its billing item and price, sample type, result lines with units and normal ranges. The lab maps each test to its MOH 706 row.

**Medication** (Healthcare › Setup): one per medicine on the formulary — the stock item it dispenses, strength, dosage form, and whether it is billable. Drug interaction and allergy checks use it when doctors prescribe.

**Prescription Dosage** (Healthcare › Setup): each dosage pattern with its times and tablets per dose. The quantity to dispense and the ward drug chart are worked out from it, so:

- Give every dosage set times, for example *1-1-1* at 09:00, 14:00 and 21:00.
- Add patterns for medicines taken several tablets at a time, for example *4-0-4* for artemether-lumefantrine (4 tablets at 09:00 and 21:00).

Demo records: *Haemoglobin (Hb)* template, *Capsule Amoxicillin 500mg* medication, *4-0-4* dosage.

![Lab Test Template](images/admin/04-lab-template.png)

*A lab test template.*

![Medication](images/admin/05-medication.png)

*A medication on the formulary.*

![Prescription Dosage 4-0-4](images/admin/06-dosage.png)

*The 4-0-4 dosage: 4 tablets at 09:00 and 21:00.*

## Step 5 — Wards, beds and their stores

**Where:** Healthcare › Service Unit (use **Healthcare Service Unit Tree** to see the whole hospital).

1. Build the tree: hospital › wards and departments › rooms and beds. Consultation rooms, labs and theatres are service units too.
2. For each bed, choose its **Service Unit Type** (for example General Ward Bed, which carries the price per night) and tick **Inpatient Occupancy**.
3. Give each bed a **Warehouse**: ward medicines are moved there by the pharmacy and issued from there when a dose is given.
4. On each ward, set the *MOH 717 Ward* category and its linen store.

Demo record: GW Bed 03 in the General Ward, type General Ward Bed, warehouse GW Bed 03 - KVHL.

![Bed with its own warehouse](images/admin/07-bed.png)

*A bed: service unit type, inpatient occupancy and its own store.*

## Step 6 — Hospital-wide settings

**Healthcare Settings** (Healthcare › Setup): tick *Manage Inpatient Medication Stock* and *Auto Schedule Medication Doses* so ward doses are tracked bed by bed (see the [Inpatient guide](03-inpatient.md)), and set the inpatient visit charge item.

**Kenya Health Settings** (Kenya Health › Setup):

| Setting | Recommended |
| --- | --- |
| Bed Charge Basis | Per night |
| Medicines Item Group | Drug |
| Pharmacy Warehouse | The pharmacy store |
| Expiry Warning (Days) | 90 |
| Minimum Days of Cover | 14 |
| Meal Billing | Included in bed charge, per day, or per meal |
| Linen Store and Laundry | Your linen stores |
| Fetal heart rate alert limit | 110 (WHO) or 120 if your form says so |
| Patient record access log | On |
| Require full registration details | On |
| Payment before service: laboratory, radiology, pharmacy | On (cash patients pay first; insured, inpatient and casualty are served first) |

Save the page once after installation, even if you change nothing, so every default is stored.

![Kenya Health Settings](images/admin/08-kenya-health-settings.png)

*Kenya Health Settings: bed charges, pharmacy, kitchen and laundry.*

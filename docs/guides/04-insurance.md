# Insurance Workflow — Step-by-Step Guide

How an insured patient is billed in RoyceERP Health: the patient pays only the copay, the insurer's share becomes a claim, and rejected lines are settled. Shown on the demo hospital at hospital.royceltd.com.

## At a glance

![One insured visit: copay, claim, rejection](images/insurance/00-flow.png)

The insurer covers 90% on this plan, so Peter paid KES 240 at the cashier. One claim line was rejected and settled by billing Peter.

## How an insured patient's bill is made and settled

1. **Check-in.** Reception chooses *Insurance*, the payer and the scheme, and the member number (Patient Visit). The patient is not asked to pay before the lab, radiology or pharmacy.
2. **As services are ordered** (consultation, tests, imaging, drugs), each gets an insurance coverage at the scheme's price and share, and goes onto the visit's **draft bill** straight away (with *Bill insured visits automatically*, Kenya Health Settings › Payment Before Service, on by default). Nobody has to press Create Bill; the visit's Bill section shows the running total and the insurer's share.
3. **When the visit is closed**, the bill is submitted: KRA eTIMS signs one invoice to the patient for the full amount; the insurer's share moves to the insurer's claims account; the **copay** (if the scheme has one) stays on the invoice as what the patient owes.
4. **The cashier** takes the copay (Step 4). If the bill could not be submitted at closing (a price or setup missing), the person closing the visit is told why, and the bill waits in draft for the cashier.
5. **The claim** (Step 5): the insurance desk puts the period's covered lines on an Insurance Claim, sends it, and records the insurer's decision. Rejected lines are billed to the patient or written off (Step 6), and the insurer's payment clears the claims account.

## Step 1 — Set up the insurer and plan (one-time)

**Who:** finance or administrator. **Where:** Insurance › Policies & Contracts.

1. **Insurance Payor:** the insurer's name, with its customer and claims receivable account so its share is tracked separately.
2. **Insurance Payor Contract:** the agreement with the insurer for the hospital, with its validity dates.
3. **Eligibility Plan:** each scheme the insurer sells (for example Corporate Gold).
4. **Item Insurance Eligibility:** for each service or drug on the plan, the share the insurer covers, for example 90% of consultation and lab, 100% of ward charges. Set *manual approval* where the insurer requires pre-authorisation.

Demo records: insurer *Mlima Health Assurance (Demo)*, plan *Corporate Gold (Demo)*, contract PAYOR-CONT-2026-00001.

### Pricebooks: a price for each payment category

A **Price List** is a pricebook. Cash patients pay the *Standard Selling* prices (the default in Selling Settings). Each scheme can have its own:

1. Stock › Price List › *+ Add*: one per tariff, ticked *Selling*. Several schemes can share one. For example:

   | Price List | Used by | Consultation |
   | --- | --- | --- |
   | Standard Selling | Cash | the doctor's fee, e.g. KES 200 |
   | SHA-PHC | SHA Primary Health Care | KES 500 |
   | SHA Schemes 1000 | SHA-Mwalimu, UASALAMA, POMSF | KES 1,000 |

2. Stock › Item Price: the price of each service in each list (or open the list and use *Import* for a whole tariff at once). Report **Item Prices** shows them side by side.
3. On each **Eligibility Plan** (scheme), set **Price List**. The insurer's contract can set a **Default Price List** for schemes that don't have one.

An insured patient's covered services are then priced from the scheme's list, and from the contract's when the scheme's list doesn't price the service. The consultation fee uses the scheme's price for the consultation item when the list has one; otherwise the doctor's fee. A service with no scheme price is charged at the cash price.

![Insurance Payor record](images/insurance/01-insurer.png)

*The insurer, with its own customer and claims account.*

![Eligibility plan](images/insurance/02-plan.png)

*The plan the patient is on.*

## Step 2 — Record the patient's policy

**Who:** reception. **Where:** Insurance › Patient Insurance Policy › *+ Add*.

1. Choose the patient, the insurer and the plan.
2. Enter the policy or member number and the validity dates from the insurance card.
3. Save. From now on, services ordered for this patient can be covered by the policy.

Check the card at every visit: an expired policy means the patient pays in full.

**At check-in:** reception can do this step on the Patient Visit instead. Choosing *Insurance* picks up the patient's policy with that payer, or creates and submits a new one from the member number, validity, relation to the principal member and the principal's details typed at the desk. The visit also keeps the limit and the authorisation code, and refuses expired cover. Insured patients are served by the lab, radiology and pharmacy without paying first. See the [Reception, queue and billing guide](12-reception-queue-billing.md), Step 2.

Demo record: policy INS-PLCY-2026-00001 for *Peter Otieno Kamau* on Corporate Gold.

![Patient Insurance Policy](images/insurance/03-policy.png)

*The patient's policy: insurer, plan, number and validity.*

## Step 3 — Services ordered under the policy get coverage

**Who:** automatic, or the insurance desk for pre-authorisation. **Where:** Insurance › Coverage.

1. When the doctor orders a service for an insured patient (consultation, test, drug, bed), the system creates a **Patient Insurance Coverage** for it with the plan's share, at the scheme's price. A patient checked in on an insured visit is covered without anything else to do: the consultation takes the visit's policy, so its orders are covered, and so is the consultation fee once the consultation is submitted.
2. Items on automatic approval are approved straight away.
3. Items the insurer must pre-authorise wait for approval: enter the insurer's approval and set the coverage to *Approved*. If the insurer declines, the patient pays in full.

Demo records: coverages INS-COV-2026-00001 to 00003 for Peter's consultation, malaria slide and WBC, each at 90%.

![Patient Insurance Coverage](images/insurance/04-coverage.png)

*One coverage per service, with the insurer's share.*

## Step 4 — Bill the full amount and collect the copay

**Who:** cashier. **Where:** the visit's bill (made automatically for insured visits, see above), or Insurance › Sales Invoice › *+ Add* for a patient without a visit.

1. On a manual invoice, choose the patient, then **Get Items From › Healthcare Services**. Each covered line carries the insurer's share.
2. Submit. The invoice shows **Total Insurance Coverage Amount** (the insurer's share) and **Patient Payable Amount** (the copay).
3. Take the copay from the patient by M-Pesa or cash.
4. The insurer's share moves automatically to the insurer's claims receivable.

There is one KRA eTIMS invoice, to the patient, for the full amount.

| Peter's invoice ACC-SINV-2026-00003 | KES |
| --- | --- |
| Invoice total (consultation, WBC, malaria slide) | 2,400 |
| Insurer's share (90%) | 2,160 |
| **Copay paid by Peter** | **240** |

![Invoice with insurance coverage and patient payable](images/insurance/05-invoice-lines.png)

*The invoice: Total KES 2,400, Insurance Coverage 2,160, Patient Payable 240.*

## Step 5 — Create the claim and record the insurer's decision

**Who:** insurance or claims officer. **Where:** Insurance › Insurance Claim › *+ Add*.

1. Choose the insurer, plan, patient and policy. The billed coverages for the visit come in as claim lines.
2. Submit the claim and send it to the insurer with the supporting documents.
3. When the insurer replies, mark each line **Approved** or **Rejected**, with the approved amount. The claim shows the approved and rejected totals.

| Peter's claim INS-CLAIM-2026-00001 | KES | Insurer's decision |
| --- | --- | --- |
| General consultation | 1,350 | Approved |
| Malaria blood slide | 450 | Approved |
| White cell count | 360 | Rejected |
| **Claimed** | **2,160** | 1,800 approved, 360 rejected |

![Insurance Claim](images/insurance/07-claim.png)

*The claim for Peter's visit.*

![Claim lines with approved and rejected](images/insurance/08-claim-lines.png)

*Claim lines: two completed, one rejected and billed to the patient; approved 1,800, rejected 360, paid 1,800.*

## Step 6 — Settle rejected lines and record the insurer's payment

**Who:** claims officer and finance. **Where:** the Insurance Claim.

1. **Settle Rejected Lines:** for each rejected line choose **Bill Patient** (the amount moves to the patient's account, to be collected like any balance) or **Write Off** (to the Rejected Insurance Claims expense account). Each settlement is a journal entry; cancelling it reopens the line.
2. **Record the payment:** when the insurer pays, create the payment from the claim. The approved lines become *Completed* and the claim's outstanding amount drops to zero.

No new KRA invoice is needed when a rejected line is billed to the patient: the patient's invoice already carried the full amount.

Demo records: the KES 360 rejected WBC line was billed to Peter (journal entry ACC-JV-2026-00004); the insurer paid KES 1,800; claim status *Completed*.

![Settlement journal entry](images/insurance/09-settlement.png)

*The settlement: the rejected KES 360 moved from the insurer's account to Peter's.*

## Tracking claims

The Kenya Health home page shows **Claims Awaiting Payment**, and the **SHA and insurance claims** chart shows, per insurer, what is not yet claimed, awaiting payment, paid and rejected. Revenue by department splits each department's income into the patients' and the insurers' share.

Still to come:

- **SHA claims** through DHA's Health Information Exchange: waiting for DHA sandbox approval, then DHA testing and certification. Keep using the SHA portal for SHA patients until then.
- **Slade360** for private insurers: waiting for API access. Until then, claims are prepared here and submitted the insurer's usual way.
- **A separate KRA invoice to the insurer:** awaiting a tax adviser's view.

![Kenya Health management dashboard](images/insurance/10-dashboard.png)

*The Kenya Health home page: claims awaiting payment and revenue split into patients' and insurers' shares.*

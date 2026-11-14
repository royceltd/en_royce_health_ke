# Petty Cash — Testing Guide

A short script to test petty cash (kenyan_accountant 16.8): requests by staff, approval by the accounts office, payment from the float, top-ups and the voucher. Each test says what to do and what the system should do. Tick each one off. If anything behaves differently, send a screenshot.

Test on the demo hospital (hospital.royceltd.com). How it works day to day: [Petty Cash guide](../16-petty-cash.md).

## Before you start

| Login | Roles | Used for |
| --- | --- | --- |
| Reception (or any staff login) | Receptionist | Requesting |
| Nurse | Nursing User | Requesting on behalf of a ward |
| Accounts | Accounts User | Approving, paying, topping up |
| A second accounts login | Accounts User | Approving the first one's own request |

## A. Request

1. **Reception:** Kenya Accounting › Petty Cash › Petty Cash Request › *+ Add*. Two lines: 4 box files at 350, 1 sanitiser at 1,800. Purpose "Triage desk supplies". Save and Submit.
   - [ ] The total is 3,200 and the request is *Pending Approval*.
   - [ ] There is no Approve button for the receptionist.
2. **Nurse:** a request with **Request on behalf of someone** ticked, for "Ward 3".
   - [ ] *Requested For* is required once the box is ticked.
3. **Reception:** open the Petty Cash Request list.
   - [ ] Only the receptionist's own requests are listed, not the nurse's.

## B. Approve, pay, print

1. **Accounts:** open the receptionist's request.
   - [ ] The blue bar shows how much petty cash holds.
2. Fill in an **Expense Account** on each line (for example Print and Stationery), then **Approve**.
   - [ ] *Approved*, with your name under Approval.
3. **Pay**: received by "Triage nurses".
   - [ ] *Paid*, with a Journal Entry. The float went down by 3,200.
   - [ ] The Journal Entry debits the expense accounts and credits Petty Cash.
4. Print: **Petty Cash Voucher**.
   - [ ] Voucher number, lines, total in words, purpose, and signature lines for requested, approved and received by.

## C. Controls

1. **Accounts:** submit a request yourself, then try to **Approve** it.
   - [ ] Refused: "You can't approve your own request". The second accounts login can.
2. Approve a request for more than the float holds, then **Pay**.
   - [ ] Refused: "… holds …, less than this request. Top it up first."
3. **Reject** a pending request without a reason.
   - [ ] A reason is required. With one, the request is *Rejected* and can't be paid.
4. Approve a request with a line that has no expense account, then **Pay**.
   - [ ] Refused until the account is filled in.
5. Cancel the Journal Entry of a paid request.
   - [ ] The request is back to *Approved*.

## D. Top up

1. **Accounts:** Petty Cash Request list › **Top Up Petty Cash**: from M-Pesa, 10,000, code "TEST123".
   - [ ] "Petty cash now holds …", higher by 10,000. The list's indicator shows the new balance.

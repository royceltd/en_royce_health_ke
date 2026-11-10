# Theatre — Testing Guide

A short script to test the theatre forms before using them with real patients. Each test says what to do and what the system should do. Tick each one off. If anything behaves differently, send a screenshot.

Test on the demo hospital (hospital.royceltd.com), not on your live site, because the tests create bookings and records. The steps are explained in full in the [Theatre guide](10-theatre.md).

## Before you start

- Log in with a user who has the doctor, nurse and theatre roles (the Administrator works).
- Use the demo patient **Grace Wanjiku Mwangi**. She has recent lab results, so test 6 can show them filling in.
- Use **Main Theatre** on a date with nothing else booked, for example next week.
- Use the procedure **Appendicectomy (open)**, a surgeon and an anaesthetist.
- Write down the booking number you create (THB-…); every test below uses it.

## A. Booking

| # | Do this | The system should |
| --- | --- | --- |
| 1 | Create a Theatre Booking: Grace, Appendicectomy (open), priority **Elective**, Main Theatre, 09:00, a surgeon and an anaesthetist. Save. | Save it as **Scheduled**, with the end time worked out from the duration. |
| 2 | Create a second booking in **Main Theatre** at 09:30 the same day, for any patient. | Refuse it with **Theatre clash**, naming your first booking. Discard it. |
| 3 | Open **Theatre List** for that date. | Show your booking. |

## B. Into Theatre: what must be done first

Use your booking from test 1. Press **Into Theatre** at each step, then fix the problem it names.

| # | Do this | The system should |
| --- | --- | --- |
| 4 | Press **Into Theatre** with nothing else done. | Refuse: *Record and submit the patient's surgical consent first.* |
| 5 | *Records › Record Consent*. Fill in what was explained, the risks, who is consenting and the witness. Submit. Print **Consent for Operation**. | Print the hospital's consent wording with Grace's name, the doctor and the operation filled in, signature lines and a thumbprint box. |
| 6 | *Records › Anaesthesia Record*. Choose the anaesthetist, ASA class and anaesthesia type. Save. | Fill in Hb, WBC and the other lab values from Grace's results, her allergies from her file, and the 24 systems-review lines. |
| 7 | On the Anaesthesia Record, enter GCS eye **5**. Save. | Refuse: *GCS eye must be between 1 and 4.* Enter E4, M6, V5: the total shows **15**. |
| 8 | *Records › Start Safety Checklist*. Save it empty. On the booking, press **Into Theatre**. | Checklist: **Consent for operation signed** is ticked by itself. Into Theatre refuses: *Complete the Surgical Safety Checklist Sign In first.* |
| 9 | On the checklist **WHO Checklist** tab, answer every **Sign In** item and enter who did it. Save. Press **Into Theatre** again. | Sign In turns **Done** with the time stamped. Into Theatre refuses: *Complete the ward preparation and handover … first.* |
| 10 | On the **Ward Preparation** tab, tick the ID band, gown and jewellery boxes, choose dentures and fasting, and enter the three handover names. Save. | Ward Preparation turns **Done** and the handover times are stamped. |
| 11 | Press **Into Theatre**. | The booking turns **In Theatre** and an **Operation Note** appears under *Records*. |

## C. In theatre

| # | Do this | The system should |
| --- | --- | --- |
| 12 | On the checklist, answer every **Sign Out** item (with the counts left empty) and enter who did it, before **Time Out**. Save. | Refuse: *Sign Out can't be completed before the phase before it.* Do Time Out first. |
| 13 | On the **Counts** tab, enter for gauze swabs: start 10, added 5, end 14. Save. | The line shows **Missing 1**. |
| 14 | On **Sign Out**, tick **counts correct**. Save. | Refuse with **The counts don't balance**, listing the gauze swabs line. |
| 15 | Correct the end count to 15. Leave the nurses' names empty. Save. | The line shows **Correct**. Saving refuses: *Name the scrub nurse and the circulating nurse who did the counts.* |
| 16 | Enter both nurses' names and finish Sign Out. Save. | Sign Out turns **Done**. |
| 17 | On the Anaesthesia Record **Anaesthesia** tab, set the end of surgery before the start. Save. | Refuse: *The end of surgery is before its start.* Correct it, then add a drug and two monitoring rows. |

## D. Completing and recovery

| # | Do this | The system should |
| --- | --- | --- |
| 18 | On the booking, press **Complete** before writing the operation note. | Refuse: *Write the operation note (procedure details) on … first.* |
| 19 | Open the Operation Note. Write the findings, the incision and the procedure details. Save. Press **Complete** on the booking. | The booking turns **Completed** and the theatre consumables are issued from stock. |
| 20 | Make a second booking, answer the **Post-operative** tab before its Sign Out, and save. | Refuse: *The post-operative checklist can't be completed before Sign Out.* |
| 21 | Back on your first checklist, answer the **Post-operative** tab: pulse, BP, level of consciousness, handed over by, received by. Save. | Post-op turns **Done** with the time back in the ward stamped. |

## E. Emergencies

| # | Do this | The system should |
| --- | --- | --- |
| 22 | Make a booking with priority **Emergency**. Submit a consent and do Sign In only, no ward preparation. Press **Into Theatre**. | Let it in, with an orange warning that ward preparation is not complete. |

## F. Prints

Print each record from your test (the printer icon, top right). The forms are the system's defaults.

| # | Print | Check |
| --- | --- | --- |
| 23 | Theatre Checklist | Four parts: ward preparation, WHO checklist, gauze and instruments with the results, post-operative. Unanswered items show empty boxes or lines. |
| 24 | Anaesthesia Record | The pre-operative assessment with the systems review, airway, labs and ASA, then the monitoring chart, drugs and recovery. |
| 25 | Operation Note | Team, anaesthesia type and agents, findings, incision, procedure and instructions. |
| 26 | Consent for Operation | As in test 5. |

## Tell us

1. Any test where the system did something different, with a screenshot.
2. Any item on your paper forms that is missing, or worded differently.
3. Do you fill in both the pre/post-operative checklist and the Surgical Safety Checklist today? We merged them into one record.
4. Does your KSA Anaesthesia Record have a third (intra-operative) page? We received two.

# Hospital server kit

A dedicated server for one hospital running RoyceERP Health: a single ERPNext site with
the health apps (Marley + royce_health_ke, royce_etims, kenyan_accountant, royce_talk,
royce_payroll_ke, royce_payments). First use: **Bethesda Healthcare Services** on a Vilcom
VPS (go-live postponed: Bethesda uses another system for a year from November 2026).

This kit is separate from Royce Cloud (the multi-tenant SME platform, its Control Plane,
Server Agent and monitoring in the royce-erp-cloud repo): a hospital needs none of those,
and its image carries private apps the platform image doesn't. The kit copies the layout
of the pilot server (`royce-test`, 80.241.222.38, where hospital.royceltd.com and
bethesda.royceltd.com run), which has been running since 7 November. The one part taken
from the platform is the backup script, `backup-to-object-storage.sh` (a copy, kept here), unchanged (its
notes: royce-erp-cloud `docs/operations/backups.md`).

| Script | Run where, as | What |
| --- | --- | --- |
| `setup-server.sh` | new server, root | admin user, key-only SSH, ufw (22, and 80/443 from Cloudflare only), fail2ban, auto security updates, swap, Docker, nginx + Cloudflare Origin certificate |
| `deploy-release.sh` | server, root | **the release path**: pulls the image GitHub Actions built (`.github/workflows/hospital-image.yml` in this repo, `ghcr.io/royceltd/royceerp-health:<tag>`), backs up, switches, migrates the sites named, checks, keeps 3 images |
| `ship-image.sh` | your laptop | copies the tested image from the pilot to the new server (no registry, no GitHub token on the hospital's server) |
| `build-image.sh` | new server, root | fallback: builds the image there (asks for a read-only GitHub token, keeps it only in memory) |
| `start-stack.sh` | new server, root | the ERPNext stack (compose project `royceerp`, MariaDB 11.8, Redis), and later upgrades |
| `move-site.sh` | your laptop | backup on the source, restore on the target, checks; `--final` freezes the source first |
| `restore-backup.sh` | server, root | restores a backup folder (move-site.sh uses it; also restore drills) |
| `setup-backups.sh` | server, root | hourly + daily encrypted backups to the hospital's own R2 bucket, failure alert |
| `hospital.env.example` | | the settings every script reads (`/opt/royceerp/hospital.env`, 600) |

Tested 2026-11-15 on the pilot: the compose file `start-stack.sh` generates is
byte-identical to the pilot's running one, and `move-site.sh` copied bethesda.royceltd.com
into a drill site on the same server with every check passing (see the end of this file).

## Releases: everything pinned

`apps.health.json` is the hospital release manifest: Frappe's apps and every Royce app at a
**tag**, never a branch (the same rule as Royce Cloud's platform releases, ADR-019).
Marley is pinned at the version `royce_health_ke` supports (`royce_health_ke/marley.py`
`SUPPORTED`, checked by its `test_marley`). To release: tag the app (`vX.Y.Z` = its
`__version__`), change its ref here, commit, build. Two builds of the same manifest have the
same code.

Release path: tests pass (GitHub Actions, every push; they use the versions in this file) →
tag the app, set its ref here, commit → **en_royce_health_ke › Actions › Hospital image › Run workflow** with the image tag
(e.g. `16-hke0.37.1`) → on the server `bash deploy-release.sh <tag> hospital.royceltd.com`
(the demo is staging: the IT team checks it) → then the other sites. No image is ever
built on a live server.

## Server to ask for

Ubuntu 24.04, **4 vCPU, 16 GB RAM** (8 GB is the minimum: the pilot's 8 GB uses 2 GB of
swap with two sites), **150 GB SSD/NVMe** (each image is 6 GB, and three are kept for
rollback; the database grows with every visit), a public IPv4 address, root SSH with our
key. **In Kenya**: patient data is "primary healthcare data" under the Data Protection
(General) Regulations 2021, reg. 26(2), which requires at least one copy in Kenya. See
"Data protection" below.

## Go-live day: the order

1. **Collect:** the server's IP and root access. Put our key on it:
   `ssh-copy-id -i ~/.ssh/royce_test root@<ip>`. Add an `~/.ssh/config` entry
   (`Host vilcom-bethesda`, `User root`, `IdentityFile ~/.ssh/royce_test`,
   `IdentitiesOnly yes`).
2. **Server** (~10 min):
   From the en_royce_health_ke checkout on your laptop (this folder is `deploy/`):
   ```bash
   scp -r deploy vilcom-bethesda:/opt/royce-kit            # the kit, backup script included
   ssh vilcom-bethesda 'mkdir -p /opt/royceerp'
   scp deploy/hospital.env.example vilcom-bethesda:/opt/royceerp/hospital.env
   ssh -t vilcom-bethesda 'nano /opt/royceerp/hospital.env'         # SITE, keys, IMAGE_TAG, bucket
   # the *.royceltd.com origin certificate, straight from the pilot:
   ssh royce-test 'cat /etc/ssl/royceltd/origin.pem' | ssh vilcom-bethesda 'cat > /root/origin.pem'
   ssh royce-test 'cat /etc/ssl/royceltd/origin.key' | ssh vilcom-bethesda 'umask 077; cat > /root/origin.key'
   ssh vilcom-bethesda 'bash /opt/royce-kit/setup-server.sh /opt/royceerp/hospital.env && shred -u /root/origin.key'
   ```
   Open a **new** terminal and log in as the admin user before closing the first one.
   The other server scripts run the same way: `sudo bash /opt/royce-kit/<script> /opt/royceerp/hospital.env`.
3. **Image** (~20-40 min, depends on the laptop's connection):
   `bash ship-image.sh royce-test vilcom-bethesda 16-hke0.29.0`
4. **Stack** (~2 min): `ssh vilcom-bethesda 'sudo bash /opt/royce-kit/start-stack.sh /opt/royceerp/hospital.env'`
5. **Rehearsal move** (~5 min): `bash move-site.sh royce-test vilcom-bethesda bethesda.royceltd.com`.
   The pilot keeps running. The copy on the new server is quiet: scheduler off, emails muted.
6. **Test the copy before DNS moves.** The firewall only lets Cloudflare in, so use a
   tunnel: `ssh -L 8080:127.0.0.1:8080 vilcom-bethesda`, then add `127.0.0.1 bethesda.royceltd.com`
   to your laptop's `/etc/hosts` and open `http://bethesda.royceltd.com:8080`. Log in and
   open a patient, the visit list, the lab and pharmacy worklists, and a print. Remove
   the hosts line when you're done.
7. **Backups** (~10 min): `sudo bash setup-backups.sh /opt/royceerp/hospital.env`. It
   needs the bucket and token (below). Then save the printed rclone.conf in the password
   manager.
8. **Final move** (when Bethesda's setup data is in and staff are about to start): drop
   the rehearsal copy (`bench drop-site bethesda.royceltd.com --db-root-password <from
   royceerp.env> --no-backup`), then `bash move-site.sh --final royce-test vilcom-bethesda bethesda.royceltd.com`.
9. **DNS:** Cloudflare › royceltd.com › DNS › add `A bethesda` → the new IP, **proxied**.
   An explicit record overrides the `*.royceltd.com` wildcard that points at the pilot.
   Check `https://bethesda.royceltd.com` loads from the new server
   (`ssh vilcom-bethesda 'sudo tail -2 /var/log/nginx/access.log'` shows your request).
10. **Afterwards:** the pilot's copy stays frozen (maintenance mode) as the fallback for
    a week, then drop it there.

**Rollback during go-live week:** point the DNS record back at the pilot, and on the pilot
run `bench --site bethesda.royceltd.com set-maintenance-mode off` and `enable-scheduler`.
Anything entered on the new server after the move would then have to be copied back by
hand, so decide early (Tuesday or Wednesday), not on Friday.

## Backups: the bucket

Make it once in Cloudflare (dashboard, R2):

1. **Create bucket** `royce-hospital-bethesda`. Location hint: the nearest offered
   (R2 has no Africa region; see "Data protection").
2. **Manage R2 API tokens › Create:** permission *Object Read & Write*, applied to that
   bucket only. Keep the Access Key ID, Secret and endpoint for `setup-backups.sh`.
3. **Settings › Object lifecycle rules** (our token can't set them):
   `crypt/hourly/` delete after 7 days, `crypt/full/` 30 days, `crypt/monthly/` 365 days,
   `crypt/files-history/` 30 days. **No rule** on `crypt/files/` (the live file mirror).
4. **Bucket lock rules** (ransomware protection): `crypt/hourly/` 3 days, `crypt/full/` 14,
   `crypt/monthly/` 90, `crypt/files-history/` 14. Never lock `crypt/files/`.

The same `setup-backups.sh` also works on the pilot server (same stack layout). Point it
at its own bucket, since the pilot has **no off-server backup today**.

**Restore drill** (in the first week, then monthly): download the newest set
(`sudo -u royce-backup rclone copy r2-crypt:crypt/full/royceltd.com/<site>/<time>/ /opt/royceerp/restore/drill/`
with `HOME=/opt/royce/backup-home`), then
`sudo bash restore-backup.sh /opt/royceerp/restore/drill <site> --as drill.royceltd.com`.
Check the output, then drop `drill.royceltd.com`.

## Upgrades

As on the pilot: build the new image on the pilot (`/opt/royceerp/build.sh <tag>`),
deploy and test it there, then `ship-image.sh` it to the hospital server. There, set
`IMAGE_TAG` in hospital.env, run `sudo systemctl start royce-backup@full`, then
`start-stack.sh` and `bench --site <site> migrate`. The previous compose file is kept for
rollback. Remove the oldest image when more than three are kept (`docker image rm`).

## Data protection

- **Hospital data must keep a copy in Kenya** (reg. 26(2), primary/secondary healthcare
  data; ADR-006 found SME data exempt, but this data is not). A server in Kenya (Vilcom)
  is that copy.
- **The pilot server is in Germany (Contabo)** and holds Bethesda's pilot data. That's
  acceptable for testing, but real patients should be on the Kenyan server from the
  parallel run on Tuesday.
- **R2 backups leave Kenya.** That needs Cloudflare's Data Processing Addendum executed
  (ADR-006, still open) and the encryption here, which is on by default. Alternative: a
  second Kenyan location (another Vilcom/Safaricom/Angani bucket or server) for backups.
  `RCLONE_REMOTE` takes any rclone remote.
- Bethesda is the data controller. Its contract with Royce must name Royce (and Vilcom,
  Cloudflare) as processors (reg. 24).

## Test record

2026-11-15, on the pilot (royce-test):
- `start-stack.sh`'s compose generation, run against the pilot's env, reproduced
  `compose.royceerp.yaml` byte for byte.
- `AS=drill-bethesda.royceltd.com bash move-site.sh royce-test royce-test bethesda.royceltd.com`:
  2.5 minutes in total (backup 15 s, copy 13 s, new site 50 s, restore 25 s, migrate 30 s).
  The checks passed: the 1 stored password decrypts, 4 of 4 uploaded files are on disk,
  and the record counts equal the source's. The copy came up quiet (scheduler off,
  emails muted), and the source was untouched (scheduler on, 200). The first run found
  a bug, now fixed: the image has no `frappe` group (`chown frappe`, not `frappe:frappe`).
  The drill site was dropped afterwards and its archive folder removed.
- Not yet run anywhere: `setup-server.sh` (needs a fresh server), `ship-image.sh`
  (needs a second server) and `setup-backups.sh` (needs the bucket).

## Restore drill log

Evidence for the Backup & Recovery policy (DHA certification asks that recovery has been
tested). Each drill restores a backup under another name with `restore-backup.sh --as`,
compares it with the source, and drops it.

| Date | Source | Backup | Restore | Checks | Result |
| --- | --- | --- | --- | --- | --- |
| 2026-11-15 | bethesda.royceltd.com (pilot) | `move-site.sh` to a drill site on the same server | drill-bethesda | all `--check` checks | Passed |
| 2026-11-17 | hospital.royceltd.com (pilot, v0.37.0) | bench backup with files, on the server (2.2 MB database, 6 files) | drill.royceltd.com, 150 s | stored passwords 2/2 decrypt; files 6/6 on disk; Patient 32, Patient Visit 30, Patient Encounter 45, Sales Invoice 37, Payment Entry 45, Lab Test 29, Medication Request 29, GL Entry 278, all equal to the source | Passed |

Not yet drilled: restoring from the **off-site** copy. The pilot has no off-site backups
(`setup-backups.sh` has not been run there: it holds only the demo and test data). Run it,
and drill from the R2 copy, before any hospital's real data is on a server.


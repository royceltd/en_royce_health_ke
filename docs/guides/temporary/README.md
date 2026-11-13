# Temporary guides

Short-lived guides that go with one release or one hospital's go-live: setup checklists, release testing scripts. They are not part of the numbered user guides (in the folder above), which describe how the system works for good.

Once a temporary guide's job is done (the hospital is set up, the release is tested), delete it, or move what lasts into the numbered guides.

| Guide | For | Release | Written |
| --- | --- | --- | --- |
| [Bethesda setup for versions 0.24 and 0.25](bethesda-setup-v0.25.md) | Bethesda's system administrator | v0.25.0 | 2026-11-13 |
| [Version 0.24 and 0.25 testing](v0.25-testing.md) | The hospital's testers, on the demo | v0.25.0 | 2026-11-13 |

PDFs: `TEMPORARY=1 node make_pdfs.mjs ../temporary "<output folder>/Temporary"` from `docs/guides/tools` (same environment variables as the numbered guides).

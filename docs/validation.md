# Source-release validation

Validated locally on 2026-09-17 without production credentials or running paid
provider requests. This is verification of the source release, not a claim that
the retired production infrastructure is still available.

## Frontend

- Installed dependencies with pnpm 10.32.1 and generated a committed lockfile
- `pnpm build` passed
- The build prerendered and verified all 24 Russian/English public routes
- Verification checked per-route metadata, canonical URLs, content, JSON-LD,
  and the separate neutral SPA shell for private routes

## Python

Installed `requirements-dev.txt` in a fresh Python 3.12 virtual environment and
ran `python -m pytest --disable-socket --allow-unix-socket`.

Result: **125 passed, 1 expected failure**. Outbound TCP connections were disabled.
The expected failure is strict: the test will fail if the marked issue starts
passing without updating its status.

The known issue is `test_planner_block_message_has_no_trailing_dot`: the archived
planner block message ends in a period, despite the historical copy preference.
This cosmetic defect is retained and explicitly reported; it does not affect the
publication's removal of credentials.

The historical Telegram flow suite is retained under `tests/legacy/` and excluded
from default discovery. It imports the removed `FLOW_TIMEOUT_SECONDS_FULL` API
and targets old flow behavior. It is not counted among passing tests or presented
as coverage of the current bot. Running it explicitly requires updating it to the
current runtime contract.

During source-release preparation, stale test fixtures were made independent of
the author's local `.env`. Storage credentials are mocked, required web settings
are synthetic, and email/verifier expectations reflect the existing sender format
and candidate-download return shape. Product pipeline behavior was not changed
to make these tests pass.

## Publication checks

- Source exported into a new repository without the private Git history
- Gitleaks 8.30.1 reported no findings in the sanitized source snapshot
- Tracked-file check rejects private/generated directories and credential files
- Legal examples and deployment settings were anonymized
- Demonstration images were approved for inclusion by the project owner
- Analytics requires explicit counter/host configuration and user consent

## Not verified

- Real model generation, marketplace search, paid checkout, email delivery, or
  Cloud Tasks dispatch against live providers
- Provisioning a new GCP environment or restoring a production database
- Full interactive browser regression testing of every app workflow
- Continued availability or compatibility of every external provider/model
- Comprehensive dependency vulnerability remediation

The CI workflow repeats secret scanning, the frontend build, and the supported
Python suite. No deployment credentials are needed. Python dependency ranges are
historical lower bounds; future package updates can require additional work.

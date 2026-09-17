# Repository guidance

VizuAI is a discontinued product released as a portfolio source archive.

- Start with README.md and docs/architecture.md. Production infrastructure and
  credentials are not included and must not be reconstructed from private copies.
- Keep secrets in environment variables or a secret manager, never in source or
  screenshots. Use synthetic data in tests and docs.
- Preserve the existing web-first architecture, separate API/worker entrypoints,
  and legacy Telegram boundary.
- Do not overwrite production prompt templates during experiments.
- Keep private notes, source-history bundles, exports, and customer images out of
  this repository.
- Run the relevant tests, frontend build for web changes, and secret scanning
  before publishing changes. Check docs/validation.md for known limitations.

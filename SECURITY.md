# Security and secrets

This is an archived portfolio project, not an operated production service.
There is no guarantee of ongoing security maintenance.

Do not put credentials, signed media URLs, authentication links, customer data,
or debug exports in issues or pull requests. Use GitHub private vulnerability
reporting if available to report a security issue without disclosing secrets.

Configuration examples contain empty credentials or local-development-only
values. Keep service-account files outside the repository. Configure your own
email, billing, storage, model, and queue integrations before using private flows.

CI checks the tracked file boundary, runs a secret scanner against Git history,
and builds the frontend. A clean scan cannot guarantee the absence of all private
data; inspect screenshots, logs, and test fixtures before adding them.

If you expose a credential, revoke or rotate it with its provider. Removing it
from the latest commit does not invalidate it or remove it from older commits.

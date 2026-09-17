# Architecture and implementation notes

VizuAI combined interior generation and furniture discovery in a web application.
The hosted product has been retired; the source captures its final configuration.

## Runtime boundaries

| Component | Entrypoint | Responsibility |
| --- | --- | --- |
| Browser | `frontend/web/src/main.tsx` | Public pages, auth, drafts, billing, results |
| Web API | `main_web.py` | Accounts, sessions, uploads, jobs, history, checkout |
| Worker | `main_worker.py` / `main.py` | Long-running AI jobs and payment webhooks |
| Legacy Telegram | `main_bot.py` / `main.py` | Bot UI and historical payment flows |

`app_services` holds web business logic. `pipeline` and `services` hold shared
processing and provider integrations. PostgreSQL stores durable accounts, drafts,
jobs, sessions, payments, and ledger entries. Cloud Tasks dispatches work outside
the HTTP request lifecycle. Cloud Storage holds image assets; browsers use
short-lived signed upload and download URLs.

## Interior design and reference design

1. Validate the request, ownership, credit balance, and uploaded assets
2. Normalize images and prepare an optional style-reference image
3. Run the planner to interpret the request and produce structured constraints
4. Assemble the rendering prompt from the planner output and prompt template
5. Generate two candidate images in one batched image-model call
6. Use an AI A/B ranker to select the preferred candidate
7. Persist the selected image and job result for delivery and history

The image stage has a retry and a Decor8 fallback. Text planning/ranking use an
OpenAI primary path and Gemini/Vertex fallback. Reference design selects separate
planner, renderer, and ranker templates. This is one shared pipeline with a
reference branch, rather than two independent implementations.

There are eight active prompt files: six design templates and two furniture
templates. The ranker performs quality selection; it is not a guarantee of
geometrical correctness or professional design suitability.

## Furniture discovery

Vision object localization produces bounding boxes. The worker prepares crops,
uploads them, obtains signed URLs, optionally generates query terms, retrieves
marketplace candidates through SearchAPI, and visually verifies shortlisted
products. It returns an annotated image and product links.

The configured sources are Ozon, Yandex Market, and Wildberries. Default limits
allow up to 60 scanned candidates per marketplace per object, up to three
shortlisted candidates per marketplace for verification, and up to five final
links. These are configured limits, not measured average retrieval volumes.

## Authentication and payments

Email magic links are delivered through Resend; a historical Postmark fallback
remains in the code. The database stores hashed link/session tokens. The frontend
uses cookie sessions and preserves locale through the login flow.

T-Bank checkout and webhooks update the payment/credit ledger. Job idempotency,
ownership checks, and saved drafts protect the return-from-payment workflow.
Returning from a payment page is not itself proof that a payment succeeded.

## Public pages and localization

Vite builds the React application and a server-render entry. A build script
prerenders 12 routes in Russian and English, for 24 HTML outputs. Metadata and
structured data are route-specific. A separate empty SPA shell serves private
routes and unknown-route fallbacks. Public language follows the URL; the app
stores language in account/client state. Some deeper app copy remains Russian.

## Tradeoffs and limitations

- Redis became optional to reduce operating cost. The fallback runtime state is
  process-local and does not provide a distributed concurrency limiter. The
  original low-traffic deployment constrained worker concurrency accordingly.
- External model/search/payment services are necessary for full end-to-end
  execution. This release does not emulate them or include access credentials.
- Historical legal and marketing copy is retained as product context, with
  anonymized operator details. It is not an active offer or a current service SLA.
- Provider/model APIs and marketplace responses evolve. Independent deployments
  need fresh integration testing and security review.
- Some legacy tests and bot paths may require maintenance. See validation.md for
  the verification performed for this source release.

# TraFriend Repository Guidance

This file applies to the entire repository. A more specific `AGENTS.md` may add rules for a subdirectory but must not weaken the security, calculation, or data-provenance rules here.

## Project mission

TraFriend is a public U.S. stock market analytics website. Its first tools are:

1. A single-day leveraged ETF theoretical price calculator anchored to Daily Close Anchors.
2. Current and historical Profit Ratio analytics.

TraFriend is an information and research product, not a brokerage, trade execution system, investment adviser, or multi-day leveraged ETF prediction engine.

## Read before changing code

Use these documents as the source of truth:

- `docs/PRD.md` for behavior, MVP scope, acceptance criteria, and open product decisions.
- `docs/ARCHITECTURE.md` for service boundaries, dependency direction, provider design, and repository structure.
- `docs/API_SPEC.md` for public transport contracts.
- `docs/DATA_MODEL.md` for persistence semantics and invariants.

The root `README.md` is user-facing. Keep it focused on what TraFriend is and how users understand the product. Do not move internal architecture, setup minutiae, database schemas, provider credentials, or agent instructions into it.

Phase 1 provides a Next.js frontend and a mock-first FastAPI backend. Keep development on the Mock provider and in-memory data until the user explicitly authorizes live provider or PostgreSQL work.

## Repository boundaries

- Keep `apps/web` and `services/api` independently buildable and deployable.
- Frontend code must not import backend source code.
- Backend financial/domain code must not import FastAPI, ORM models, provider SDKs, or frontend concepts.
- Share API shapes through a reviewed OpenAPI contract/generated TypeScript client, not through duplicated cross-language domain logic.
- Prefer feature-oriented modules. Do not create broad `utils`, `helpers`, or “god service” modules when a narrower home exists.
- Add a new financial tool as a vertical module with its own domain rules, application use cases/ports, adapters, API routes, frontend feature, and tests.
- Extract shared abstractions only after at least two real consumers demonstrate the same stable concept.

## Frontend rules

- Stack: Next.js, TypeScript, Tailwind CSS, and shadcn/ui.
- UI components render state and collect input; they do not own or reimplement authoritative financial formulas.
- All market and analytics data comes through the TraFriend backend API. Do not call a market data vendor directly from browser code.
- Keep generic shadcn/ui primitives free of market-domain logic.
- Use the generated API contract when available; do not hand-maintain competing response types.
- Treat API decimal strings deliberately. Do not allow implicit JavaScript floating-point conversion to change displayed financial values.
- Implement explicit loading, empty, unavailable, stale, and error states for every data view.
- Preserve accessibility: semantic HTML, keyboard operation, visible focus, labels, accessible chart alternatives, and WCAG 2.2 AA contrast.
- Only public, non-sensitive values may use `NEXT_PUBLIC_*`. A market data key is never public configuration.

## Backend rules

- Stack: Python and FastAPI; PostgreSQL is introduced when persistence work begins.
- Use dependency direction: presentation -> application -> domain. Infrastructure implements application ports and is wired at the composition root.
- FastAPI route handlers only validate/translate HTTP concerns and invoke use cases. No formula, SQL, or provider SDK logic in routes.
- ORM models stay in infrastructure. Map them to domain/application types at repository boundaries.
- Use timezone-aware UTC instants and an injected U.S. exchange calendar for trading dates and session behavior.
- Use Python `Decimal` for authoritative prices, leverage, ratios, returns, and calculations. Do not use binary floating point for financial rules.
- Return typed domain/application errors and map them to stable public error codes. Never leak vendor errors, stack traces, connection details, or secrets.
- Calculation reads use stored complete Daily Close Anchors and must not make a live provider request.

## Financial calculation rules

The initial formula is a single-day theoretical linear relationship:

```text
underlying_return = underlying_target / underlying_reference - 1
leveraged_return  = signed_leverage_factor * underlying_return
leveraged_target  = leveraged_reference * (1 + leveraged_return)
```

Reverse calculation:

```text
leveraged_return  = leveraged_target / leveraged_reference - 1
underlying_return = leveraged_return / signed_leverage_factor
underlying_target = underlying_reference * (1 + underlying_return)
```

Guardrails:

- Signed leverage is metadata from an active relationship, not user-supplied authoritative input.
- Reference prices come from one active immutable Daily Close Anchor version, not from the client.
- Inputs and references must be finite and positive; leverage must be finite and non-zero.
- A computed price less than or equal to zero is outside the model domain. Return a clear error; never clamp it to zero or show it as a valid price.
- Do not add compounding, volatility decay, fees, distributions, tracking error, or multi-day prediction to this formula without an approved product/architecture change.
- Preserve full calculation precision and round only according to the approved serialization/display policy.
- Keep a visible `formula_version` in API results.

Every formula change requires automated unit tests, boundary tests, signed-leverage coverage, and forward/reverse round-trip coverage. A UI snapshot or manual calculator check is not sufficient.

## Daily Close Anchor rules

- Capture one coherent underlying/leveraged ETF pair from the latest completed U.S. regular-session closes.
- Derive the completed trading date and actual close instant through the exchange calendar; do not equate it with server `CURRENT_DATE` or wall-clock hour.
- Validate price positivity, expected same trading date, provider/feed provenance, quality, currency, and timestamps.
- Publish a pair only after both daily closes are valid and stored atomically.
- Never silently mix providers, dates, sessions, relationships, or anchor versions in one calculation.
- Never silently fall back to an earlier session when the expected completed-session close is missing, stale, or delayed at the provider.
- Capture retries are idempotent. Corrections create a higher immutable version, record a reason, and preserve the prior version/audit history.
- Public results include anchor version/type, trading date, market timestamps, provider/feed labels, and single-day warning.
- Keep `OVERNIGHT_OPEN` and `OVERNIGHT_SNAPSHOT` infrastructure separate from calculator anchors. Their diagnostic policies do not define the daily reset boundary.

## Provider rules

- Declare narrow interfaces in the application layer, such as instrument catalog, quotes, Profit Ratio, repositories, clock, and trading calendar.
- Place concrete Mock, Futu/OpenD, or other vendor adapters in backend infrastructure.
- Provider SDK response objects must not cross the adapter boundary.
- Normalize provider data into canonical IDs, `Decimal` values, UTC timestamps, currency, provenance, and stable error categories.
- Keep capability checks explicit. Do not fabricate unsupported Profit Ratio history or OHLC.
- Every adapter must pass a shared provider contract suite.
- The Mock provider is required and is the default for local development and normal CI. It must offer deterministic normal, inverse, missing, stale, partial, holiday, and boundary fixtures.
- Ordinary tests must not require network access, live markets, or provider credentials.

## Profit Ratio rules

- Profit Ratio is provider/methodology-dependent. Do not implement a guessed definition.
- Store and return a methodology key/version, provider, observation time, trading date, and quality state with every series.
- Keep values in fractional units and enforce the inclusive range `[0, 1]`.
- Do not silently merge incompatible methodology versions, interpolate gaps, or forward-fill missing values.
- Profit Ratio OHLC is allowed only when multiple genuine observations support meaningful open/high/low/close values and bar boundaries are documented.
- Keep historical comparison price bars separate from Daily Close Anchors.

## Security and secrets

- Never commit credentials, tokens, certificates, private provider URLs, or real `.env` files.
- Market data credentials belong only in backend/worker runtime secrets or a managed secret store.
- Never send credentials or privileged provider details in frontend bundles, API payloads, logs, fixtures, screenshots, exceptions, or analytics events.
- `.env.example` may contain variable names and safe descriptions only.
- Redact authorization headers and provider secrets from structured logs.
- Validate and length/range-limit all public input. Add rate limits before public production release.
- Use least-privilege runtime, worker, migration, and database roles.

If a secret is discovered, stop exposing it, report the affected location without repeating the value, and follow the repository's rotation/remediation process.

## API and data compatibility

- Public HTTP routes live under `/api/v1` and follow `docs/API_SPEC.md`.
- Serialize authoritative decimals as strings and timestamps as UTC RFC 3339.
- Treat ticker text as mutable display/search data; use canonical instrument IDs internally.
- Use effective dates for leveraged-product relationships and immutable versions for reference/observation history.
- Additive optional response fields are preferred. Breaking schema or semantic changes require an explicit version/migration plan.
- Keep a reviewed generated OpenAPI snapshot once the API exists and test frontend-client drift in CI.
- Do not expose capture/admin operations as unauthenticated public routes.

## Testing expectations

Changes must be tested at the lowest reliable layer:

- Pure domain unit/property/boundary tests for calculations and invariants.
- Application tests with fake clocks, calendars, providers, and repositories.
- Provider contract tests shared by Mock and real adapters.
- PostgreSQL integration tests for migrations, constraints, transactions, and idempotency.
- API tests for schemas and stable error mapping.
- Frontend component tests for states and formatting.
- End-to-end tests for search-to-calculation and Profit Ratio history.

Do not weaken assertions, broaden tolerances without a documented rounding decision, or replace deterministic fixtures with calls to a live provider. When toolchains exist, run the smallest relevant suite during iteration and the documented full checks before handoff.

## Documentation and decision discipline

- Update documentation in the same change when behavior, formulas, API fields, persistence semantics, session rules, security posture, or deployment boundaries change.
- Add an architecture decision record under `docs/adr/` for choices with long-lived alternatives or migration cost.
- Preserve the distinction between approved behavior and an open decision. Do not implement an open decision by accident.
- Document provider licensing/redistribution constraints before storing or serving live market data.
- Comments should explain non-obvious intent or market semantics, not restate code.

## Change hygiene

- Inspect the working tree before editing and preserve unrelated user changes.
- Keep changes scoped to the request. Do not mix formatting churn, dependency upgrades, or unrelated refactors into a feature.
- Do not edit generated files manually.
- Do not invent setup/test commands before manifests exist. Once toolchains are added, document canonical commands in developer documentation under `docs/`.
- Do not commit IDE-specific project files as part of application work unless the repository explicitly adopts them.

## Definition of done

A feature change is complete only when:

- Behavior matches the PRD and API contract or those documents were deliberately updated.
- Domain and dependency boundaries remain intact.
- Financial and data invariants have automated tests.
- Mock-based development and normal CI remain credential-free and deterministic.
- Error, stale, missing, and boundary paths are handled, not only the happy path.
- User-facing timestamps, provenance, methodology, and disclosures are present where required.
- No secret can reach the browser or repository.
- Relevant tests, static checks, and migrations pass, and the handoff states what was verified.

## Permanent development-round reporting

Every development round must end with a structured section titled exactly `TRAFRIEND PROGRESS SUMMARY`. The section is intended to be copied into a new ChatGPT conversation and must stand on its own. It always contains these numbered parts:

1. **ROUND** — short name of the development round.
2. **GOAL** — what the round was intended to accomplish.
3. **COMPLETED** — concrete work completed, including important files/modules created or modified.
4. **CURRENT ARCHITECTURE** — only the architecture relevant after this round and what changed; do not repeat the entire architecture.
5. **TEST RESULTS** — exact commands executed, passed/failed counts, and applicable lint/typecheck/build results. Never claim tests passed without naming what ran.
6. **MANUAL VERIFICATION** — what was manually tested, exact symbols/data, and actual observed results when real data was used.
7. **DATA PROVIDER STATUS** — implemented provider(s); whether each has been tested with Mock, historical real data, or live real data; known real-time/delayed/unknown state and plan/feed limits.
8. **KNOWN ISSUES / RISKS** — remaining technical/data-quality uncertainty and anything that blocks the next phase.
9. **NOT IMPLEMENTED YET** — major planned features intentionally absent.
10. **NEXT RECOMMENDED STEP** — exactly one recommended next development round.
11. **USER ACTION REQUIRED** — credentials, account setup, timed manual checks, or `None`.
12. **GIT STATUS** — current branch, whether changes are uncommitted, and a suggested commit message. Never push or merge unless explicitly instructed.

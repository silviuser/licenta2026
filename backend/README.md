# HR Helper — Application Backend

Spring Boot backend that orchestrates the NLP microservice and exposes a
JWT-protected REST API for the frontend client.

```
Frontend (SPA)  ──REST/JSON + JWT──►  Backend (Spring Boot :8080 + PostgreSQL)  ──HTTP──►  NLP Service (FastAPI :8000)
```

- **Java 21**, **Spring Boot 3.3**, **Gradle** (Kotlin DSL)
- **PostgreSQL** + Spring Data JPA, schema via **Flyway**
- PDFs stored in Postgres as `bytea`
- **JWT** auth (HS256), roles `RECRUITER` / `ADMIN`, strict per-user isolation
- Hand-written **WebClient** NLP client
- **Asynchronous** matching: create a job, poll for status

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| JDK | 21 (LTS) | `JAVA_HOME` must point at it |
| PostgreSQL | 16 | local instance on `:5432` |
| Docker | any | only for the integration tests (Testcontainers) |
| NLP service | — | FastAPI on `:8000` (see `../nlp-service/api/README.md`) |

The Gradle wrapper (`./gradlew`) downloads Gradle itself — no global install needed.

## 2. Database setup

A local Postgres with a `hrhelper` database and a `hrhelper` login role is expected:

```sql
CREATE ROLE hrhelper LOGIN PASSWORD 'hrhelper';
CREATE DATABASE hrhelper OWNER hrhelper;
```

Flyway applies `src/main/resources/db/migration/V1..V4` automatically on startup.

## 3. Run

```powershell
# from app/backend
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot"
.\gradlew.bat bootRun
```

Backend starts on `:8080`. With the NLP service running on `:8000`, the full
matching flow works end-to-end.

- Swagger UI: <http://localhost:8080/swagger-ui.html>
- OpenAPI JSON: <http://localhost:8080/v3/api-docs>
- Liveness: <http://localhost:8080/api/health>

## 4. Configuration (env vars, prefix `HRHELPER_BACKEND_`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `HRHELPER_BACKEND_PORT` | `8080` | Backend port |
| `HRHELPER_BACKEND_DB_URL` | `jdbc:postgresql://localhost:5432/hrhelper` | DB connection |
| `HRHELPER_BACKEND_DB_USER` | `hrhelper` | DB user |
| `HRHELPER_BACKEND_DB_PASSWORD` | `hrhelper` | DB password |
| `HRHELPER_BACKEND_JWT_SECRET` | dev placeholder | JWT signing secret (set in prod!) |
| `HRHELPER_BACKEND_JWT_EXPIRY_MIN` | `120` | Token lifetime (minutes) |
| `HRHELPER_BACKEND_NLP_BASE_URL` | `http://localhost:8000` | NLP service URL |
| `HRHELPER_BACKEND_NLP_TIMEOUT_SEC` | `60` | NLP call timeout (warmup-tolerant) |
| `HRHELPER_BACKEND_MAX_PDF_MB` | `20` | Max CV upload size (aligned with NLP) |
| `HRHELPER_BACKEND_CORS_ALLOW_ORIGINS` | `http://localhost:5173,http://localhost:3000` | CORS origins (comma-separated) |
| `HRHELPER_PUBLIC_BASE_URL` | `http://localhost:5173` | Base URL the public apply link is built from (SPA serves `/apply/{token}`) |
| `HRHELPER_PUBLIC_RL_GET` | `60` | Public `GET /api/public/**` rate limit per IP per minute |
| `HRHELPER_PUBLIC_RL_POST` | `10` | Public `POST /api/public/**` (applications) rate limit per IP per hour |

## 5. API surface

All under `/api`, JSON, JWT-protected except register/login/health **and `/api/public/**`**.

| Area | Endpoints |
|------|-----------|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| CVs | `POST /api/cvs` (multipart, 1..N `files`, optional `?jdId`) → `202` per-file results; `GET /api/cvs`, `GET /api/cvs/{id}`, `GET /api/cvs/{id}/file`, `PATCH /api/cvs/{id}/email` `{manualEmail}` (REWORK 4 D45), `DELETE /api/cvs/{id}` |
| JDs | `POST /api/jds` `{title, descriptionText, requirements?}`, `GET /api/jds`, `GET /api/jds/{id}`, `PUT /api/jds/{id}`, `PUT /api/jds/{id}/requirements`, `DELETE /api/jds/{id}` |
| Applications | `POST /api/jds/{id}/applications` `{cvIds}`, `GET /api/jds/{id}/applications`, `DELETE /api/jds/{id}/applications/{applicationId}` |
| Matching | `POST /api/jds/{id}/match` `{sourceJdIds}` → `202 {jobId, status}`; `GET /api/matches/{jobId}`; `GET /api/matches?jdId=&status=` |
| Dashboard | `GET /api/dashboard` → KPIs + per-position summary (REWORK 2 D30) |
| Apply link (recruiter) | `POST /api/jds/{id}/apply-link` (generate/regenerate + enable), `PUT /api/jds/{id}/apply-link` `{enabled}`, `GET /api/jds/{id}/apply-link` → `{exists, enabled, url}` (REWORK 3 D33) |
| Public apply (no JWT) | `GET /api/public/apply/{token}` → `{jobTitle, jobDescription}`; `POST /api/public/apply/{token}` multipart `{name, email, phone, file}` → `201 RECEIVED` / `200 UPDATED` (REWORK 3 D32–D39) |
| Admin | `GET /api/admin/users` (ADMIN only) |
| Ops | `GET /api/health`, `GET /api/nlp/info` (proxy of NLP `/v1/info`) |

### Background processing (REWORK 1)

- **CV upload (D17/D21/D22):** `POST /api/cvs` accepts 1..N PDFs, dedups by SHA-256
  per owner, returns `202` immediately with a per-file result
  (`CREATED` / `DUPLICATE` / `REJECTED`). A dedicated executor then extracts each
  new CV (`/v1/extract`, cached on the CV) and flips its `processingStatus` to
  `READY` (or `FAILED`). When `?jdId` is set, an `Application` is created per file.
- **JD creation (D18):** `POST /api/jds` with no `requirements` but a
  `descriptionText` returns immediately as `PENDING`; the executor calls
  `/v1/extract-jd` and populates `Requirement`s (`source=EXTRACTED`). The recruiter
  edits the list via `PUT /api/jds/{id}/requirements`.

### Matching flow (per-JD, async — D24/D25, selective pooling D27–D29)

1. `POST /api/jds/{id}/match {sourceJdIds}` → persists a `PENDING` per-JD
   `MatchJob` (`cvId` null), returns `jobId`. `sourceJdIds` are the other positions
   to pool applications from (empty = direct applications only). Each source is
   validated: owned by the recruiter (else `404`) and not the target itself (else
   `400 source_includes_target`). The legacy `include_other_applications` column is
   kept read-only and set to `!sourceJdIds.isEmpty()`.
2. The executor builds the deduplicated CV pool (direct applications + applications
   from the selected `sourceJdIds`, deduped by content hash, `DIRECT` winning over
   pooled). Pooled candidates record their provenance (`source_jd_id` /
   `source_jd_title`). It obtains each CV's cached extraction (extracting lazily if
   needed, never failing the whole job), calls `/v1/match` per CV, and stores a
   deterministic ranked report in `result_json` (plus a denormalised `top_score`).
3. Poll `GET /api/matches/{jobId}` until `SUCCEEDED` (the `result` is the
   `MatchReport`: ranked candidates with matched/missing skills + a generated
   explanation) or `FAILED` (`errorCode` + `errorDetail`).

### Dashboard (REWORK 2 D30)

`GET /api/dashboard` returns the landing read model in one call: KPIs (open
positions, unique candidates, CVs processing, last finished match) plus a
per-position summary (application count + latest match status/top score). All
aggregates are computed with dedicated count/group-by/projection queries — no
N+1, no entity-collection loading.

### Public candidate apply link (REWORK 3 D32–D39)

Candidates apply with **no account** — the link is the credential (a capability
URL). Per JD the recruiter can generate/regenerate the token, copy the link, and
toggle it on/off (`/api/jds/{id}/apply-link`). Regenerating overwrites the token,
so the old link instantly 404s.

- **Token (D32):** 32 random bytes from `SecureRandom`, URL-safe Base64 (~256 bits),
  stored unique on `job_descriptions.apply_token`. Resolved by indexed lookup; never
  logged.
- **Public flow (D34–D36):** `POST /api/public/apply/{token}` validates name/email/
  phone + the PDF (content-type **and** `%PDF-` magic bytes), then dedups on
  `(jd, email)` — a returning candidate's CV is **replaced** and contact details
  refreshed (the superseded CV is removed if nothing else references it). Byte-identical
  files reuse the existing CV (SHA-256, no reprocessing). The CV enters the recruiter's
  library (owner = JD owner) and the **same background extraction pipeline** (D39); the
  application is tagged `origin=CANDIDATE_LINK` with the candidate's details (surfaced
  in the applications list and the match report, D37).
- **Hardening (D38):** only `/api/public/**` is `permitAll` (CSRF stays disabled,
  stateless). An in-memory per-IP rate limiter (`PublicRateLimitFilter`, no new
  infra) throttles GET/POST; responses expose no internal ids, recruiter identity,
  or other candidates' data; a missing/disabled token returns a **generic 404**.
- **Not done (future work):** no CAPTCHA on the public endpoint yet — a sensible next
  hardening step against automated submissions, on top of the per-IP rate limit.

### Contact actions (REWORK 4 D40–D47)

Each CV gets an **email mined from its text** by the NLP service (`/v1/extract` now
returns an additive `contact: {emails, primary_email}` block; the regex runs over
the already-extracted text — no second PDF parse). It is stored on `cvs.extracted_email`;
the recruiter can override it via `PATCH /api/cvs/{id}/email` (`cvs.manual_email`),
and clearing it reverts to the extracted value (server-side syntactic validation,
owner-scoped per D6).

- **Effective email (D42):** resolved in one place (`EmailResolution`) with precedence
  **public-form (candidate link) → manual → extracted → none**, exposed pre-resolved on
  the match report (`CandidateReport.effectiveEmail` + `emailSource`), the applications
  list, and `CvResponse`. The match value is a snapshot at match time — a later manual
  edit shows in the next match (D45).
- **Backfill (D46):** on startup, READY CVs with no email are re-processed in the
  background on the existing `extractExecutor`, in rate-limited batches that never block
  startup. Idempotent and NLP-frugal: a CV whose cache already carries a `contact` block
  derives the email locally; only legacy caches trigger a fresh `/v1/extract`.
- **No SMTP (D43):** the app never sends mail — the frontend uses `mailto:` (BCC for
  multi-candidate, D47) and clipboard only.
- **Phase 2 (not done now):** sending email from the app (SMTP), templates, a
  contact/send history, and phone/LinkedIn extraction. Contact extraction is carried on
  the extensible `contact` block so adding fields later needs no schema break.

## 6. Tests

```powershell
.\gradlew.bat test      # requires Docker running (Testcontainers Postgres)
```

- **Unit** (no Spring context): `JwtTokenProviderTest`, `ExplanationServiceTest`
  (deterministic report text), `MatchPoolServiceTest` (hash dedup + provenance),
  `ApplyTokenGeneratorTest` (entropy/URL-safe/uniqueness), `PdfFileSupportTest`
  (magic bytes + SHA-256), `ApplyLinkServiceTest` (generate/regenerate/toggle).
- **Integration** (Testcontainers Postgres + Flyway + a MockWebServer NLP stub):
  `AuthFlowIT`, `CvControllerIT` (bulk upload, dedup, per-user isolation),
  `JdControllerIT`, `JdExtractionFlowIT` (JD from text → extracted requirements →
  edited), `ApplicationControllerIT` (attach/list/detach), `JdMatchFlowIT` (per-JD
  match: ranked report; pooling with `includeOtherApplications` deduped),
  `PublicApplyFlowIT` (apply via link → recruiter sees candidate → enters match;
  disabled/regenerated token → 404; email+JD dedup with CV replacement; file
  validation; per-user isolation), `PublicRateLimitIT` (POST budget → 429).

## 7. Notes

- The NLP service pays a 5–10 s warmup on its first call; the WebClient timeout
  defaults to 60 s to tolerate it. Transient NLP failures (503 / unreachable)
  get one retry; 4xx validation errors never do.
- `X-Request-ID` is generated per request and propagated to the NLP service for
  cross-service log correlation.
- The loaded NLP encoder is the Step 5 placeholder — scores are structurally
  correct but compressed in range. `pipeline_version` is stored on every job for
  traceability (surfaced via `GET /api/nlp/info`).

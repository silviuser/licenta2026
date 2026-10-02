# HR Helper — Frontend

Single-page app (SPA) that gives the recruiter a UI on top of the HR Helper
Spring Boot backend: upload CVs, define job descriptions with structured
requirements, run an **asynchronous** CV↔JD match (poll until done), and review
the score breakdown and history.

The frontend talks **only** to the backend (`:8080`) — never directly to the
NLP service.

```
Frontend SPA (React + Vite :5173)  ──REST/JSON + JWT──►  Backend (:8080)  ──►  NLP service
```

## Stack

- **React 18 + TypeScript** (strict), **Vite**
- **Material UI (MUI v5)** — all design tokens live in [`src/theme/theme.ts`](src/theme/theme.ts)
- **TanStack Query (React Query)** — data cache + match polling
- **Axios** with JWT request interceptor and a 401 → login interceptor
- **React Router v6**
- **Vitest + React Testing Library + MSW** for tests

## Prerequisites

- Node.js ≥ 20, npm ≥ 10
- The backend running on `:8080` (see [`../backend/README.md`](../backend/README.md)).
  Vite's dev origin `http://localhost:5173` is already in the backend CORS list.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `http://localhost:8080` | Backend base URL |

Copy `.env.example` to `.env` to override (the `.env` file is git-ignored):

```powershell
Copy-Item .env.example .env
```

## Run (development)

```powershell
npm install
npm run dev
```

Open <http://localhost:5173>. The first screen is **Sign in**; create an account
from the **Create account** link if you don't have one yet (registration signs
you in automatically and lands on the **CVs** page).

## Scripts

| Script | What it does |
|--------|--------------|
| `npm run dev` | Start Vite dev server on `:5173` |
| `npm run build` | Type-check (`tsc -b`) and build for production into `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run typecheck` | `tsc --noEmit` on the app sources |
| `npm run lint` | ESLint |
| `npm run format` | Prettier (write) |
| `npm test` | Run the Vitest suite once |
| `npm run test:watch` | Vitest in watch mode |

## Demo flow (what to show the committee)

1. **Register / sign in** → lands on **CVs**.
2. **Upload a CV** (PDF, drag & drop or button). It appears in the table with
   size, detected language, and an "extraction cached" badge.
3. **Job Descriptions → Create job description**: give it a title and at least
   one requirement (each is *required* or *nice-to-have*, with an optional skill
   label and confidence).
4. **Run match** (from a CV row or **Match → Run a match**): pick a CV + a JD.
   The result page shows **"Analyzing the CV and scoring it against the job…"**
   and **polls every 2 s**. The first match on a fresh CV is slower (PDF
   extraction + NLP warmup).
5. On success: a big **score**, the **class** (Strong / Possible / No match),
   **coverage bars** for required and nice-to-have skills, and the lists of
   covered requirements (with the CV skill that satisfied each) vs. gaps.
6. **History**: every match, paginated and filterable by CV / JD / status;
   click a row to reopen its result.

> The NLP encoder is the Step-5 placeholder — scores are structurally correct
> but compressed in range. The pipeline version is shown discreetly on the
> result page and in the **ⓘ NLP info** popover in the top bar.

## Project structure

```
src/
├── api/        axios client + interceptors, per-resource calls, TS types (mirror of the backend contract)
├── auth/       AuthProvider/context, ProtectedRoute, JWT storage
├── hooks/      React Query hooks (useCvs, useJds, useMatchJob polling, …)
├── components/ ScoreBadge, CoverageBar, RequirementList, FileUpload, RequirementEditor, Layout, …
├── pages/      Login, Register, CVs, JDs, JdEdit, NewMatch, MatchResult, History
├── lib/        scoreColor, formatters, error-message mapping, constants/UX copy
├── theme/      MUI theme — single source of truth for the design tokens
└── test/       Vitest setup + MSW handlers/fixtures
```

Conventions: strict TypeScript; network calls go only through `api/`; pages use
React Query hooks rather than calling axios directly; no hardcoded colours/spacing
in components — everything reads from the MUI theme.

## Notes on the API contract

Backend DTOs are **camelCase**. The match job's `result` field is the raw NLP
tree and is **snake_case** — it is intentionally **not** re-mapped. Both shapes
are reflected verbatim in [`src/api/types.ts`](src/api/types.ts).

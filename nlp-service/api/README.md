# HR Helper NLP Service — FastAPI surface

Step 10 deliverable. This directory wraps the framework-agnostic
`skill_matcher` / `skill_extractor` / `cv_extractor` triple in an HTTP
service. The package is intentionally **not** part of the wheel —
production deployment is by source checkout, not by `pip install
nlp-service`.

The service exposes five `v1` endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/extract` | PDF → enriched skill candidates (Module 1 + 2 + 3 Linker). |
| `POST` | `/v1/match` | Enriched candidates + JD requirements → match result (Module 3 Scorer). |
| `POST` | `/v1/full` | PDF + JD requirements → match result (end-to-end). |
| `GET` | `/v1/info` | Versions, encoder identity, locked Step 8 thresholds, placeholder caveat. |
| `GET` | `/v1/health` | Liveness (process up). |
| `GET` | `/v1/readyz` | Readiness (encoder + ESCO index loaded). |

The auto-generated OpenAPI specification is served at `/docs` (Swagger
UI) and `/openapi.json` (machine-readable). Java client generation
should target `/openapi.json` rather than hand-rolling DTOs.

## 1. Install

The API surface ships under an optional `[api]` extra. Module 3
requires the `[ml]` extra in addition.

```powershell
cd C:\Users\silvi\Desktop\licenta2026\app\nlp-service
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,ml]" --extra-index-url https://download.pytorch.org/whl/cpu
```

The `--extra-index-url` is required on Windows to fetch CPU-only PyTorch
wheels.

## 2. Run

### 2.1 Development

```powershell
$env:HRHELPER_API_WARMUP_ON_STARTUP = "false"
uvicorn api.main:app --reload --port 8000
```

`warmup_on_startup=false` skips the 5–10 s encoder + ESCO load on every
reload. The first request to `/v1/extract` pays it instead.

### 2.2 Production

```powershell
python -m api
```

Or, with explicit uvicorn flags for systemd/Docker supervisors:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`workers=1` is the recommended default — each worker loads its own ~500 MB
encoder copy. Scale horizontally across hosts (containers, replicas)
rather than vertically within one process.

### 2.3 Running with a Java client locally

The future Java Spring Boot backend listens on `:8080` in dev. The NLP
service defaults to `:8000` so both can run simultaneously on `localhost`
without a port collision. Override with `HRHELPER_API_PORT=9000` if a
third service needs `:8000`.

## 3. Configuration

All settings are env-var overridable with the `HRHELPER_API_` prefix.

| Variable | Default | Purpose |
|----------|---------|---------|
| `HRHELPER_API_HOST` | `0.0.0.0` | Bind interface. |
| `HRHELPER_API_PORT` | `8000` | Listen port. |
| `HRHELPER_API_WORKERS` | `1` | uvicorn workers (encoder is loaded per worker). |
| `HRHELPER_API_WARMUP_ON_STARTUP` | `true` | Eager model load in the lifespan startup hook. |
| `HRHELPER_API_LOG_LEVEL` | `info` | Root structlog level (`debug` / `info` / `warning` / `error`). |
| `HRHELPER_API_REQUEST_ID_HEADER` | `X-Request-ID` | Correlation-ID header name. |
| `HRHELPER_API_MAX_PDF_SIZE_MB` | `20` | Upload size cap. |
| `HRHELPER_API_CORS_ALLOW_ORIGINS` | `[]` | JSON list of CORS-allowed origins. |

### 3.1 CORS for a local React/Vue dev server

```powershell
# PowerShell single-line form — note the literal JSON list:
$env:HRHELPER_API_CORS_ALLOW_ORIGINS = '["http://localhost:3000"]'
uvicorn api.main:app --port 8000
```

On bash:

```bash
HRHELPER_API_CORS_ALLOW_ORIGINS='["http://localhost:3000"]' uvicorn api.main:app --port 8000
```

The empty default disables CORS entirely — production deployments go
behind a reverse proxy that handles CORS itself.

## 4. Endpoint reference

### 4.1 `POST /v1/extract`

```bash
curl -X POST http://127.0.0.1:8000/v1/extract \
    -F "cv_id=alice" \
    -F "cv_pdf=@cv.pdf"
```

200 response (truncated):

```json
{
  "cv_id": "alice",
  "detected_language": "en",
  "candidates": [
    {
      "esco_uri": "http://data.europa.eu/esco/skill/...",
      "skill_label": "Python",
      "surface_form": "Python",
      "section": "skills",
      "source": "lexical_kept",
      "confidence": 0.85,
      "semantic_similarity": 0.72
    }
  ],
  "pipeline_version": "skill_matcher@0.7.0+encoder=mnrl_sw_v1_20260516",
  "warnings": []
}
```

Error responses use the uniform `ErrorResponse` schema:

```json
{ "error": "pdf_corrupt", "detail": "malformed pdf trailer", "request_id": "..." }
```

### 4.2 `POST /v1/match`

```bash
curl -X POST http://127.0.0.1:8000/v1/match \
    -H "Content-Type: application/json" \
    --data @match_request.json
```

`match_request.json` body:

```json
{
  "cv_id": "alice",
  "enriched": {  /* the full ExtractResponse from /v1/extract */ },
  "jd_id": "role-42",
  "requirements": [
    { "text": "Python", "importance": "required", "confidence": 0.9 },
    { "text": "Apache Camel", "importance": "nice_to_have", "confidence": 0.5 }
  ]
}
```

200 response (truncated):

```json
{
  "cv_id": "alice",
  "jd_id": "role-42",
  "overall_score": 0.072,
  "overall_class": "strong",
  "required_coverage": 1.0,
  "nice_to_have_coverage": 0.0,
  "matched_required": [ ... ],
  "matched_nice_to_have": [],
  "unmatched_required": [],
  "unmatched_nice_to_have": [ ... ],
  "timestamp": "2026-05-17T12:00:00Z",
  "pipeline_version": "skill_matcher@0.7.0+encoder=mnrl_sw_v1_20260516"
}
```

### 4.3 `POST /v1/full`

```bash
curl -X POST http://127.0.0.1:8000/v1/full \
    -F "cv_id=alice" \
    -F "jd_id=role-42" \
    -F 'requirements=[{"text":"Python","importance":"required"}]' \
    -F "cv_pdf=@cv.pdf"
```

200 response has the same shape as `/v1/match`.

### 4.4 `GET /v1/info`

```bash
curl http://127.0.0.1:8000/v1/info
```

200 response:

```json
{
  "nlp_service_version": "0.1.0",
  "skill_matcher_version": "0.7.0",
  "skill_extractor_version": "0.2.0",
  "cv_extractor_version": "0.2.0",
  "encoder_path": "...models/skill_matcher/mnrl_sw_v1_20260516",
  "encoder_sha": "abcdef123456",
  "esco_sha": "deadbeef0000",
  "locked_thresholds": {
    "drop_threshold": 0.40,
    "keep_threshold": 0.50,
    "expansion_threshold": 0.75,
    "per_requirement_keep_threshold": 0.085,
    "required_weight": 0.50,
    "t1_strong_threshold": 0.060,
    "t2_possible_threshold": 0.005
  },
  "placeholder_caveat": "The currently-loaded encoder is the Step 5 placeholder..."
}
```

### 4.5 Health and readiness

```bash
curl http://127.0.0.1:8000/v1/health  # always 200 if process is up
curl http://127.0.0.1:8000/v1/readyz   # 200 when warm, 503 when cold
```

`/v1/readyz` is the Kubernetes-style readiness probe — point a reverse
proxy or load-balancer's health check at it.

## 5. Java Spring Boot client (documentation example)

> This is a documentation example, not production code; client
> generation from `/openapi.json` is the recommended production path.

```java
// File: HrHelperNlpClient.java — illustrative only; thesis appendix reference.
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class HrHelperNlpClient {
    private final WebClient webClient;

    public HrHelperNlpClient(String baseUrl) {
        this.webClient = WebClient.builder()
            .baseUrl(baseUrl)                       // e.g. http://localhost:8000
            .build();
    }

    public Mono<MatchResponse> matchFull(String cvId, String jdId,
                                         byte[] cvPdfBytes,
                                         String requirementsJson) {
        MultipartBodyBuilder mp = new MultipartBodyBuilder();
        mp.part("cv_id", cvId);
        mp.part("jd_id", jdId);
        mp.part("requirements", requirementsJson);  // JSON-encoded list[RequirementSchema]
        ByteArrayResource pdfResource = new ByteArrayResource(cvPdfBytes) {
            @Override public String getFilename() { return "cv.pdf"; }
        };
        mp.part("cv_pdf", pdfResource).contentType(MediaType.APPLICATION_PDF);

        return webClient.post()
            .uri("/v1/full")
            .contentType(MediaType.MULTIPART_FORM_DATA)
            .header("X-Request-ID", java.util.UUID.randomUUID().toString())
            .bodyValue(mp.build())
            .retrieve()
            .bodyToMono(MatchResponse.class);       // generate this DTO from /openapi.json
    }
}
```

A production client should:

- Generate every DTO (`MatchResponse`, `CandidateSchema`, …) from
  `/openapi.json` using OpenAPI Generator's `spring` or `java`
  template — do not hand-roll them.
- Configure timeouts: ≥ 30 s for cold-start tolerance,
  ≥ 5 s for warm requests at P90.
- Wire the `X-Request-ID` header through to Spring's MDC so the
  Java logs and the Python logs can be joined on the correlation ID.
- Retry transient 5xx responses (the service is stateless); never
  retry 4xx.

## 6. Authentication and TLS

Out of scope for Step 10. The recommended production layout:

- Run the FastAPI service on a private network segment.
- Front it with a reverse proxy (nginx, Caddy, Traefik) that
  terminates TLS and applies an auth policy (mTLS or a shared
  secret header).
- The future Java backend is the only intended caller and lives in
  the same private segment.

## 7. Where the report lives

The Step 10 latency profile lives at
`reports/latency_profile_<YYYYMMDD>.md`, generated by
`scripts/latency_profile.py`. The numbers in that report — alongside
the Module 3 final validation report
(`reports/module3_final_validation_20260517.md`) — are what the thesis
chapter cites for production realism.

# HR Helper — Automated Recruitment & Semantic Skill Matching Platform

HR Helper este o platformă modernă end-to-end destinată optimizării proceselor de recrutare tehnică. Sistemul automatizează ingestia și parsarea CV-urilor, clasificarea competențelor conform taxonomiei europene **ESCO v1.2.1** și calcularea compatibilității dintre profilul candidatului și cerințele fișei de post (Job Description) utilizând reprezentări semantice dense (**Sentence-BERT** fine-tuned).

---

## 🏗️ Arhitectura Sistemului

Aplicația este structurată pe o arhitectură orientată pe servicii decuplate (Service-Oriented Architecture):

```
┌────────────────────────────────────────────────────────┐
│                   Frontend Client                      │
│            React 18 + TypeScript + Vite                │
│             MUI v5 / Tailwind CSS / SPA                │
│                     (Port :5173)                       │
└──────────────────────────┬─────────────────────────────┘
                           │ REST / JSON (JWT Auth)
                           ▼
┌────────────────────────────────────────────────────────┐
│                   Backend Service                      │
│          Spring Boot 3.3 (Java 21) + Flyway            │
│         Orchestrare Joburi Asincrone + Securitate      │
│                     (Port :8080)                       │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
   PostgreSQL 16 Storage                  │ HTTP / JSON
   (Entități, Istoric,                    │ (WebClient)
    Migrații V1-V12)                      ▼
                      ┌────────────────────────────────────────┐
                      │              NLP Service               │
                      │          FastAPI (Python 3.11)         │
                      │  Extracție PDF/OCR + SBERT Matcher     │
                      │              (Port :8000)              │
                      └────────────────────────────────────────┘
```

---

## 🚀 Tehnologii și Module

### 1. Backend Core (`/backend`)
- **Runtime:** Java 21 (LTS), Spring Boot 3.3
- **Persistență & Migrații:** PostgreSQL 16, Spring Data JPA, Hibernate, Flyway (migrații versionate V1–V12)
- **Securitate:** Spring Security, autentificare stateless pe bază de token-uri JWT (HS256), izolare multi-utilizator
- **Procesare Asincronă:** Ingestie asincronă de CV-uri (`extractExecutor`), job-uri de scoring neblocante cu mecanism de polling, backfill și autorecuperare automată la pornire
- **Documentație API:** Springdoc OpenAPI / Swagger UI

### 2. Frontend SPA (`/frontend`)
- **Stack:** React 18, TypeScript (strict), Vite
- **UI / Styling:** Material UI (MUI v5) cu tematică centralizată și design responsive
- **State & Server Cache:** TanStack Query (React Query) pentru cache eficient și polling periodic al stării joburilor de analiză
- **Navigare & Rețea:** React Router v6, Axios cu interceptori automați pentru token-uri JWT și reautentificare 401

### 3. NLP Microservice (`/nlp-service`)
- **Framework:** FastAPI, Uvicorn, Python 3.11
- **Modul 1 — Extracție Documente:**
  - Pipeline hibrid robust: **pdfplumber** (extracție structurală precisă a coloanelor) + **PyMuPDF** (viteză și acuratețe) + **Tesseract OCR** (fallback automat pentru documente scanate)
  - Calcul automat al scorului de calitate a textului extras și detecție limbă (Română / Engleză)
- **Modul 2 — Skill Extractor & ESCO Linker:**
  - Tokenizare, lematizare și potrivire lexico-semantică pe baza ontologiei **ESCO v1.2.1** (peste 13.800 de concepte de abilități)
- **Modul 3 — Semantic Skill Matcher:**
  - Bi-Encoder bazat pe Sentence-BERT (`all-MiniLM-L6-v2`) reantrenat specific pe perechi de competențe tehnice folosind **Multiple Negatives Ranking Loss (MNRL)**
  - Algoritm de agregare a compatibilității: cerințe obligatorii (*Required*) vs opționale (*Nice-to-have*), detecție lipsuri (*Gaps*) și evidențe contextuale din CV

### 4. Training & Experimente (`/notebooks`)
- **`skill_matcher_training.ipynb`**: Mediu reproductibil pentru antrenarea și evaluarea modelului de embedding pe Google Colab (calcul metrici MRR@10, Precision@k, Recall@k).

---

## 📂 Structura Proiectului

```
.
├── backend/                   # Microserviciul principal Spring Boot (Java 21)
│   ├── src/main/java/         # Controllere, servicii, entități, securitate
│   ├── src/main/resources/    # Configurații application.yml, migrații db/migration
│   ├── build.gradle.kts       # Configurare build Gradle
│   └── README.md              # Documentație detaliată backend
├── frontend/                  # Interfața utilizator React SPA
│   ├── src/                   # Componente UI, pagini, hook-uri, clienți API
│   ├── package.json           # Dependențe npm
│   └── README.md              # Documentație detaliată frontend
├── nlp-service/               # Serviciul de procesare limbaj natural (FastAPI)
│   ├── api/                   # Rutele HTTP v1 (/extract, /match, /full, /health)
│   ├── src/cv_extractor/      # Pipeline parsare PDF și OCR
│   ├── src/skill_extractor/   # Extracție entități și lematizare
│   ├── src/skill_matcher/     # Linker ESCO, bi-encoder SBERT, logica de scoring
│   ├── pyproject.toml         # Configurare pachet Python și dependențe
│   └── README.md              # Documentație detaliată NLP service
├── notebooks/                 # Experimente ML și scripturi de antrenare
│   └── skill_matcher_training.ipynb
├── run-all.ps1                # Lansare servicii în ferestre PowerShell separate
├── start-all.ps1              # Lansare integrată servicii în tab-uri Windows Terminal
└── README.md                  # Ghidul principal al proiectului
```

---

## ⚡ Cerințe Preliminare

| Componentă | Versiune minimă | Rol |
|---|---|---|
| **Java (JDK)** | 21 LTS | Rulare backend Spring Boot |
| **Node.js** | 20+ (cu npm 10+) | Compilare și dev server frontend |
| **Python** | 3.11 | Rulare microserviciu NLP și modele ML |
| **PostgreSQL** | 16 | Bază de date relațională |
| **Tesseract OCR** | 5.x *(opțional)* | Necesar doar pentru parsarea CV-urilor scanate |

---

## 🛠️ Configurare și Instalare

### 1. Baza de Date PostgreSQL
Creează baza de date locală și utilizatorul asociat:
```sql
CREATE USER hrhelper WITH PASSWORD 'hrhelper';
CREATE DATABASE hrhelper OWNER hrhelper;
GRANT ALL PRIVILEGES ON DATABASE hrhelper TO hrhelper;
```
*Notă: Tabelele și schemele sunt create automat la pornirea backend-ului prin migrațiile Flyway.*

### 2. Microserviciul NLP (Python)
```powershell
cd nlp-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,ml]" --extra-index-url https://download.pytorch.org/whl/cpu
```

### 3. Frontend (React)
```powershell
cd frontend
npm install
```

---

## ▶️ Rularea Aplicației

### Opțiunea A: Pornire Automată (Recomandat pe Windows)
Din rădăcina proiectului:
```powershell
# Deschide toate cele 3 servicii în tab-uri organizate de Windows Terminal:
.\start-all.ps1

# Pentru oprirea tuturor serviciilor:
.\start-all.ps1 -Stop
```
*Alternativ, poți folosi `.\run-all.ps1` dacă preferi ferestre PowerShell separate.*

### Opțiunea B: Pornire Manuală per Serviciu

1. **Pornire NLP Service** (Port `8000`):
   ```powershell
   cd nlp-service
   .\.venv\Scripts\Activate.ps1
   uvicorn api.main:app --host 127.0.0.1 --port 8000
   ```

2. **Pornire Backend** (Port `8080`):
   ```powershell
   cd backend
   .\gradlew.bat bootRun
   ```

3. **Pornire Frontend** (Port `5173`):
   ```powershell
   cd frontend
   npm run dev
   ```

---

## 🌐 Puncte de Acces Locale

- **Interfață Web Recrutor:** [http://localhost:5173](http://localhost:5173)
- **Documentație Backend (Swagger UI):** [http://localhost:8080/swagger-ui.html](http://localhost:8080/swagger-ui.html)
- **Documentație NLP Service (Interactive OpenAPI Docs):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **NLP Healthcheck:** [http://localhost:8000/v1/health](http://localhost:8000/v1/health)

---

## 🔒 Securitate și Protecția Datelor

- **Date anonimizate:** Acest depozit conține exclusiv cod sursă, taxonomii publice și date sintetice de test. Niciun CV cu caracter personal sau date de contact reale nu este stocat în istoricul de versiuni.
- **Credențiale:** Toate configurările sensibile utilizează variabile de mediu cu valori implicite destinate strict mediilor locale izolate de dezvoltare.

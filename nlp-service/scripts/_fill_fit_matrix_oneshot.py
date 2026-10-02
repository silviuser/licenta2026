"""One-shot script to fill the (CV x JD) fit_matrix.

Judgments are organised JD-by-JD (each list is in CV order:
real_cv1, real_cv2, ..., real_cv15) — this matches how a recruiter
actually thinks: "for THIS role, who would I shortlist?".

Three buckets:
  strong    - clear core-tech match, would call for interview
  possible  - partial match / transferable skills
  no        - off-domain, no meaningful overlap
"""

import csv
from pathlib import Path

MATRIX_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "eval_corpus"
    / "fit_matrix.csv"
)

CV_IDS = [f"real_cv{i}" for i in range(1, 16)]
JD_IDS = [f"jd{i}" for i in range(1, 21)]


# Each JD entry: 15 judgments in CV order (cv1 .. cv15).
# Rationale comments capture the dominant signal so this matrix is
# auditable when test_real_corpus_complete starts complaining.
JUDGMENTS: dict[str, list[str]] = {
    # Junior Java @Luxoft - Bucharest, backend
    "jd1": [
        "possible",   # cv1  Silviu (Java + OOP, junior, no Spring)
        "possible",   # cv2  Adina (Java listed but Python-heavy)
        "possible",   # cv3  Olariu (Java + JS frontend mix)
        "possible",   # cv4  Dragos (Java in skills, multi-stack)
        "possible",   # cv5  Silviu-final (Java mentioned, embedded focus)
        "no",         # cv6  Saraev (data analyst, no Spring/Java)
        "no",         # cv7  Marincovici (cybersec, Python+React)
        "possible",   # cv8  Angelescu (Java in skills, QA focus)
        "possible",   # cv9  Andreea (Java + Python data)
        "no",         # cv10 Tobescu (only C/HTML/JS)
        "strong",     # cv11 Mitroi (Java + Spring Boot + PostgreSQL explicit)
        "possible",   # cv12 Diaconescu (Java + many, gamedev)
        "no",         # cv13 Paliciuc (frontend React/Next, no Java)
        "possible",   # cv14 Diana (Java 1 Associate cert, basic)
        "no",         # cv15 Radulescu (security, no Java)
    ],
    # Junior Java Backend @Qualitest - Java + Spring Boot + Kafka + Elasticsearch
    "jd2": [
        "possible",   # cv1
        "possible",   # cv2
        "possible",   # cv3
        "possible",   # cv4
        "possible",   # cv5  (has Node/REST API — distributed mindset)
        "no",         # cv6
        "no",         # cv7
        "possible",   # cv8
        "possible",   # cv9
        "no",         # cv10
        "strong",     # cv11 (Spring Boot explicit)
        "possible",   # cv12
        "no",         # cv13
        "possible",   # cv14
        "no",         # cv15
    ],
    # Junior Fullstack @BearingPoint - HTML/CSS, JS, PHP, MSSQL, Linux, SSL/TLS
    "jd3": [
        "no",         # cv1
        "no",         # cv2
        "strong",     # cv3  (JS + HTML/CSS + Linux + Node strongest)
        "possible",   # cv4  (JS + Node + Express)
        "possible",   # cv5  (React + Node + Linux)
        "no",         # cv6
        "possible",   # cv7  (React + Linux + Tailwind)
        "strong",     # cv8  (HTML/CSS + JS + Java + multi-stack)
        "possible",   # cv9  (Node + Express + MySQL)
        "possible",   # cv10 (HTML/CSS + JS basic)
        "possible",   # cv11 (JS + CSS + React)
        "possible",   # cv12 (JS + React + Node)
        "strong",     # cv13 (React/Next + MySQL + frontend strongest)
        "no",         # cv14
        "no",         # cv15
    ],
    # Backend Developer - Java 8+, Spring Boot, Git, Docker, Cloud (AWS/GCP/Azure)
    "jd4": [
        "possible",   # cv1
        "possible",   # cv2
        "possible",   # cv3
        "possible",   # cv4
        "possible",   # cv5
        "no",         # cv6
        "no",         # cv7
        "possible",   # cv8
        "possible",   # cv9
        "no",         # cv10
        "strong",     # cv11 (Spring Boot + PostgreSQL)
        "possible",   # cv12
        "possible",   # cv13 (Docker + Azure, no Java)
        "possible",   # cv14
        "no",         # cv15
    ],
    # Embedded SWE - C++, OOP, multithreading, CMake, real-time, Linux (Defense, Bucharest)
    "jd5": [
        "possible",   # cv1  (C/C++ + OOP)
        "possible",   # cv2  (C++ in skills)
        "no",         # cv3
        "no",         # cv4
        "strong",     # cv5  (C advanced + Assembly + Real-Time + Linux PERFECT match)
        "no",         # cv6
        "no",         # cv7
        "no",         # cv8
        "no",         # cv9
        "no",         # cv10
        "no",         # cv11
        "strong",     # cv12 (C, C++, Assembly, CMake, OpenGL, GPU low-level)
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
    # Java Software Engineer - Java 11+, Spring, PostgreSQL/Sybase, JPA, REST, Linux
    "jd6": [
        "possible",   # cv1
        "possible",   # cv2
        "possible",   # cv3
        "possible",   # cv4
        "possible",   # cv5
        "no",         # cv6
        "no",         # cv7
        "possible",   # cv8
        "possible",   # cv9
        "no",         # cv10
        "strong",     # cv11 (Spring Boot + PostgreSQL)
        "possible",   # cv12
        "no",         # cv13
        "possible",   # cv14
        "no",         # cv15
    ],
    # Android Audio SWE - C/C++ audio, Android NDK, OpenSL ES/AAudio, ALSA
    "jd7": [
        "possible",   # cv1
        "no",         # cv2
        "no",         # cv3
        "strong",     # cv4  (Android app dev — Employ.me explicit)
        "possible",   # cv5  (Android listed in technologies)
        "no",         # cv6
        "no",         # cv7
        "possible",   # cv8
        "possible",   # cv9
        "no",         # cv10
        "possible",   # cv11 (Android coursework)
        "possible",   # cv12 (C++ + multi-platform)
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
    # SAP Production Engineer (devops, mid) - SAP BCS, ABAP, Linux, Python, Ansible
    "jd8": [
        "no",         # cv1
        "no",         # cv2
        "no",         # cv3
        "no",         # cv4
        "possible",   # cv5  (Linux + security mindset, no SAP)
        "possible",   # cv6  (SQL heavy, financial domain @Allianz)
        "possible",   # cv7  (Linux + Python + security ops)
        "no",         # cv8
        "no",         # cv9
        "no",         # cv10
        "no",         # cv11
        "no",         # cv12
        "no",         # cv13
        "no",         # cv14
        "possible",   # cv15 (SOC ops mindset)
    ],
    # Application Support DevOps (mid) - Java app servers, Oracle/SQL, AWS/Azure, Docker/K8s, CI/CD
    "jd9": [
        "no",         # cv1
        "no",         # cv2
        "possible",   # cv3  (Linux + Git + Java basics)
        "possible",   # cv4
        "possible",   # cv5  (Linux + Git + multi-tech)
        "possible",   # cv6
        "possible",   # cv7
        "possible",   # cv8
        "possible",   # cv9
        "no",         # cv10
        "possible",   # cv11
        "no",         # cv12
        "strong",     # cv13 (Docker + Azure explicit, frontend ops profile)
        "no",         # cv14
        "possible",   # cv15
    ],
    # Python Developer - Python, algorithms, AWS, Ansible, Linux, Git
    "jd10": [
        "possible",   # cv1  (Python in skills, junior)
        "strong",     # cv2  (Python Dev Intern @ISS, Streamlit)
        "no",         # cv3
        "strong",     # cv4  (Python AI projects + Selenium scraping)
        "possible",   # cv5  (Python in stack, Linux/Git)
        "strong",     # cv6  (Python+Pandas+scikit+PyTorch core stack)
        "strong",     # cv7  (Python+React+Linux security tools)
        "strong",     # cv8  (Python+automation+Playwright/Selenium)
        "strong",     # cv9  (Python+pandas+scikit+REST APIs data science)
        "no",         # cv10
        "possible",   # cv11
        "possible",   # cv12
        "no",         # cv13
        "no",         # cv14
        "possible",   # cv15 (Python via Pandas)
    ],
    # SWE in Test - Java test frameworks (JUnit/Cucumber), ISTQB, REST APIs
    "jd11": [
        "possible",   # cv1
        "strong",     # cv2  (Software Testing + SQC in skills, Java listed)
        "possible",   # cv3
        "possible",   # cv4
        "possible",   # cv5
        "no",         # cv6
        "possible",   # cv7
        "strong",     # cv8  (QA Engineer + Playwright/Selenium + Java)
        "possible",   # cv9
        "no",         # cv10
        "possible",   # cv11 (Software Quality and Testing coursework)
        "strong",     # cv12 (QA Tester @EA + Java)
        "no",         # cv13
        "possible",   # cv14
        "no",         # cv15
    ],
    # Full Stack Engineer (Java + .Net) — SENIOR 5+ years
    "jd12": [
        "possible",   # cv1  (Java + C# .NET basics, but junior)
        "possible",   # cv2
        "no",         # cv3
        "possible",   # cv4
        "no",         # cv5
        "no",         # cv6
        "no",         # cv7
        "possible",   # cv8
        "possible",   # cv9
        "no",         # cv10
        "possible",   # cv11
        "possible",   # cv12
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
    # AWS Data Engineer - Redshift, Airflow, DBT, Python, data warehouse
    "jd13": [
        "no",         # cv1
        "possible",   # cv2
        "no",         # cv3
        "no",         # cv4
        "no",         # cv5
        "strong",     # cv6  (advanced SQL + Pandas + Power BI/DAX data eng profile)
        "no",         # cv7
        "no",         # cv8
        "strong",     # cv9  (Python+pandas+EDA+clustering+SQL+NoSQL data sci)
        "no",         # cv10
        "possible",   # cv11
        "no",         # cv12
        "no",         # cv13
        "no",         # cv14
        "possible",   # cv15
    ],
    # Junior Big Data SWE - Python/Scala, Spark, Airflow, AWS
    "jd14": [
        "no",         # cv1
        "possible",   # cv2
        "no",         # cv3
        "possible",   # cv4
        "no",         # cv5
        "strong",     # cv6  (data analyst + Python ML stack)
        "no",         # cv7
        "no",         # cv8
        "strong",     # cv9  (data science profile + Python)
        "no",         # cv10
        "possible",   # cv11
        "no",         # cv12
        "no",         # cv13
        "no",         # cv14
        "possible",   # cv15
    ],
    # QA Automation Mobile - iOS/Android testing, Python/Java scripting, Agile, AI test tools
    "jd15": [
        "no",         # cv1
        "possible",   # cv2  (Software Testing + Python)
        "no",         # cv3
        "possible",   # cv4  (Android dev not testing)
        "possible",   # cv5
        "no",         # cv6
        "possible",   # cv7  (testing for security, somewhat)
        "strong",     # cv8  (QA + Playwright/Selenium + AI testing PERFECT)
        "no",         # cv9
        "no",         # cv10
        "possible",   # cv11 (Software Quality + Android coursework)
        "strong",     # cv12 (QA @EA + game dev mobile/PC)
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
    # Junior Embedded Crypto @NXP - C, Assembly, Cryptography, ARM Cortex M, RISC V
    "jd16": [
        "possible",   # cv1  (C/C++ in skills)
        "no",         # cv2
        "no",         # cv3
        "no",         # cv4
        "strong",     # cv5  (C adv + Assembly + Cryptography + Security PERFECT)
        "no",         # cv6
        "possible",   # cv7  (Cryptography from security work)
        "no",         # cv8
        "no",         # cv9
        "possible",   # cv10 (only C basic)
        "no",         # cv11
        "strong",     # cv12 (C + C++ + Assembly + GLSL low-level)
        "no",         # cv13
        "possible",   # cv14 (Arduino + IoT — embedded-adjacent)
        "no",         # cv15
    ],
    # C# Developer - C#, HTML, JS, PowerShell, VS, DB
    "jd17": [
        "strong",     # cv1  (C# .NET applications explicit)
        "strong",     # cv2  (C# .NET in skills)
        "no",         # cv3
        "possible",   # cv4  (C# in skills list)
        "no",         # cv5
        "no",         # cv6
        "no",         # cv7
        "strong",     # cv8  (C# + Java + HTML/CSS + JS + SQL full match)
        "possible",   # cv9  (C# in skills)
        "no",         # cv10
        "possible",   # cv11 (C# + JS + CSS)
        "strong",     # cv12 (C# + game dev with Cosmos kernel)
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
    # Software developer (C++) - C++, Windows, Linux, STL, BOOST, CMake or Makefiles
    "jd18": [
        "possible",   # cv1  (C/C++ + OOP)
        "possible",   # cv2  (C++ listed)
        "no",         # cv3
        "no",         # cv4
        "strong",     # cv5  (C++ + Assembly + Linux + OS Fundamentals + Real-Time)
        "no",         # cv6
        "no",         # cv7
        "no",         # cv8
        "no",         # cv9
        "possible",   # cv10
        "no",         # cv11
        "strong",     # cv12 (C++ + CMake + OpenGL + Linux + game engine)
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
    # Junior LowCode @SoftServe - Microsoft Power Platform, Power Automate Desktop, RPA
    "jd19": [
        "no",         # cv1
        "no",         # cv2
        "no",         # cv3
        "no",         # cv4
        "no",         # cv5
        "possible",   # cv6  (Power BI experience — Power Platform adjacent)
        "no",         # cv7
        "possible",   # cv8  (AI/automation + MCP servers)
        "no",         # cv9
        "no",         # cv10
        "no",         # cv11
        "no",         # cv12
        "no",         # cv13
        "strong",     # cv14 (RPA + Automation + GenAI certs — best match)
        "no",         # cv15
    ],
    # .NET Developer - .NET Core, C#, MVC, WebAPI, Entity Framework, SQL, K8s, Redis, GCP
    "jd20": [
        "strong",     # cv1  (.NET + C# + SQL applications)
        "strong",     # cv2  (C# .NET + SQL + Python)
        "no",         # cv3
        "possible",   # cv4
        "no",         # cv5
        "no",         # cv6
        "no",         # cv7
        "strong",     # cv8  (C# + SQL + test automation + many tools)
        "possible",   # cv9  (C# + SQL)
        "no",         # cv10
        "possible",   # cv11 (C# + SQL + Spring Boot)
        "strong",     # cv12 (C# + game dev with Cosmos kernel)
        "no",         # cv13
        "no",         # cv14
        "no",         # cv15
    ],
}


def main() -> None:
    # Transpose JD-keyed scores into CV-keyed rows.
    rows: dict[str, dict[str, str]] = {cv: {} for cv in CV_IDS}
    for jd in JD_IDS:
        scores = JUDGMENTS[jd]
        assert len(scores) == 15, f"{jd} has {len(scores)} scores"
        for cv, score in zip(CV_IDS, scores):
            rows[cv][jd] = score

    with MATRIX_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["cv_id", *JD_IDS])
        for cv in CV_IDS:
            writer.writerow([cv, *(rows[cv][jd] for jd in JD_IDS)])

    # Print distribution summary.
    print("Per-JD distribution:")
    for jd in JD_IDS:
        s = JUDGMENTS[jd].count("strong")
        p = JUDGMENTS[jd].count("possible")
        n = JUDGMENTS[jd].count("no")
        print(f"  {jd:5s}: strong={s:2d} possible={p:2d} no={n:2d}")

    total_strong = sum(v.count("strong") for v in JUDGMENTS.values())
    total_possible = sum(v.count("possible") for v in JUDGMENTS.values())
    total_no = sum(v.count("no") for v in JUDGMENTS.values())
    print()
    print(f"Totals: strong={total_strong} possible={total_possible} no={total_no} "
          f"(sum={total_strong + total_possible + total_no})")


if __name__ == "__main__":
    main()

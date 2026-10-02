"""Manual review pass over real_cv1..12 bootstrap cv_labels.

For each CV the script does three things:
- promotes obvious medium-confidence entries to high when the skill is
  explicitly named in the PDF;
- moves Module-2 false positives (duplicates, off-domain ESCO terms,
  ESCO-jargon-noise) to ``skills_definitely_not_in_cv`` keyed by their
  label;
- optionally appends a small number of glaringly-missing skills the
  bootstrap missed.

Rule of thumb: only the patterns that survive a quick eyeball pass over
the PDF — nothing here tries to be exhaustive.
"""

from pathlib import Path
import yaml

LABELS_DIR = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "eval_corpus"
    / "cv_labels"
)


# Per-CV plan:
#   promote_to_high:  list of labels currently 'medium' that we bump to 'high'.
#   move_to_fp:       list of labels to drop from gold_skills and add to
#                     skills_definitely_not_in_cv (as plain label strings).
#   add_gold:         list of (skill_uri, label, confidence) tuples to append
#                     when the bootstrap clearly missed an explicit skill.
#   notes:            fresh notes line — replaces the boilerplate bootstrap note.
PLAN: dict[str, dict] = {
    "real_cv1": dict(
        promote_to_high=[
            "IntelliJ IDEA",
            "C#",
            "Object-Oriented Programming",
            "Java (computer programming)",
            ".NET",
            "algorithms",
            "SQL",
            "database management systems",
            "Python (computer programming)",
            "database",
        ],
        move_to_fp=["Algorithms"],
        add_gold=[
            ("CUST:cpp", "C/C++", "high"),
            ("CUST:plsql", "PL/SQL", "high"),
            ("CUST:database-design", "Database Design", "high"),
            ("CUST:oracle-db", "Oracle Database", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Silviu Serban, ASE-CSIE 2nd "
            "year. Removed duplicate Algorithms (CUST) — the ESCO "
            "'algorithms' entry covers it. Promoted explicit programming "
            "stack to high; added PL/SQL, C/C++, Database Design, Oracle "
            "Database which were missing from the bootstrap."
        ),
    ),
    "real_cv2": dict(
        promote_to_high=[],
        move_to_fp=["think creatively"],
        add_gold=[
            ("CUST:cpp", "C++", "high"),
            ("CUST:oop", "Object-Oriented Programming", "high"),
            ("CUST:software-testing", "Software Testing", "high"),
            ("CUST:signal-processing", "Signal Processing", "medium"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Adina Daria Stefanescu, "
            "Python Developer Intern (ISS) + Graphic Designer @Alfa Omega. "
            "'think creatively' is a Module 2 soft-skill FP — not named "
            "explicitly. Added missing C++, OOP, Software Testing, "
            "Signal Processing (all in the Skills line of the PDF)."
        ),
    ),
    "real_cv3": dict(
        promote_to_high=[],
        move_to_fp=["logic"],
        add_gold=[
            ("CUST:html-css", "HTML/CSS", "high"),
            ("CUST:react", "React", "high"),
            ("CUST:express", "Express.js", "high"),
            ("CUST:cpp", "C++", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Olariu Razvan, ASE-CSIE. "
            "'logic' is too generic to be a real skill (ESCO noise). "
            "Added HTML/CSS, React, Express.js, C++ — all explicit in "
            "Technical Skills line."
        ),
    ),
    "real_cv4": dict(
        promote_to_high=[
            "BeautifulSoup",
            "Android (mobile operating systems)",
            "OpenAI API",
            "Web Scraping",
        ],
        move_to_fp=["football"],
        add_gold=[
            ("CUST:flask", "Flask", "high"),
            ("CUST:cpp", "C/C++", "high"),
            ("CUST:selenium", "Selenium", "high"),
            ("CUST:git", "Git", "high"),
            ("CUST:bash", "Bash", "medium"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Dragos Rudencu, ASE - "
            "Economic Informatics. 'football' = volunteer/hobby (he plays "
            "for ASE Bucharest), not a technical skill. Promoted "
            "BeautifulSoup / Android / OpenAI API / Web Scraping — all "
            "explicit in the project descriptions. Added Flask, C/C++, "
            "Selenium, Git, Bash from Technical Skills."
        ),
    ),
    "real_cv5": dict(
        promote_to_high=[
            "Cryptography",
            "algorithms",
            "Java (computer programming)",
            "Python (computer programming)",
            "Real-Time Systems",
        ],
        move_to_fp=["logic", "communication", "Algorithms"],
        add_gold=[
            ("CUST:c", "C", "high"),
            ("CUST:cpp", "C++", "high"),
            ("CUST:assembly", "Assembly x86", "high"),
            ("CUST:git", "Git", "high"),
            ("CUST:secure-coding", "Secure Coding", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Silviu Serban final-year "
            "(embedded-systems profile). Dropped duplicate 'Algorithms' "
            "(CUST) — kept the ESCO 'algorithms' and promoted to high. "
            "'logic' and 'communication' are Module-2 ESCO noise. "
            "Promoted Cryptography, Java, Python, Real-Time Systems to "
            "high — all explicit in the SKILLS block. Added C, C++, "
            "Assembly x86, Git, Secure Coding."
        ),
    ),
    "real_cv6": dict(
        promote_to_high=["database", "Python (computer programming)"],
        move_to_fp=[
            "similitude",
            "musical genres",
            "perform cleaning duties",
            "report facts",
            "Source (digital game creation systems)",
            "surveying",
            "electrical machines",
            "hang wallpaper",
            "lead others",
        ],
        add_gold=[
            ("CUST:sql", "SQL", "high"),
            ("CUST:pandas", "Pandas", "high"),
            ("CUST:scikit-learn", "scikit-learn", "high"),
            ("CUST:pytorch", "PyTorch", "high"),
            ("CUST:power-bi", "Power BI", "high"),
            ("CUST:dax", "DAX", "medium"),
            ("CUST:gbm", "Gradient Boosting (GBM)", "high"),
            ("CUST:random-forest", "Random Forest", "high"),
            ("CUST:cpp", "C/C++", "medium"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Saraev Alexandru-Ioan, "
            "Junior Portfolio Analyst @Allianz. Heavy FP cleanup — "
            "Module 2 hallucinated similitude / musical genres / perform "
            "cleaning duties / report facts / Source / surveying / "
            "electrical machines / hang wallpaper / lead others, none of "
            "which appear in the PDF. Added the real stack from the "
            "Technologies line: SQL, Pandas, scikit-learn, PyTorch, "
            "Power BI, DAX, GBM, Random Forest, C/C++."
        ),
    ),
    "real_cv7": dict(
        promote_to_high=["Metasploit", "Secure Coding"],
        move_to_fp=[
            "dies",
            "process qualitative information",
            "sales department processes",
            "optimise production",
        ],
        add_gold=[
            ("CUST:burp-suite", "Burp Suite", "high"),
            ("CUST:nmap", "Nmap", "high"),
            ("CUST:penetration-testing", "Penetration Testing", "high"),
            ("CUST:vulnerability-assessment", "Vulnerability Assessment", "high"),
            ("CUST:threat-modeling", "Threat Modeling", "high"),
            ("CUST:react", "React", "high"),
            ("CUST:tailwind", "Tailwind CSS", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Marincovici Alexandru "
            "Cristian, Cybersecurity specialist. Cleaned obvious Module 2 "
            "FPs: 'dies' (likely from 'verify… die'), 'process qualitative "
            "information' (soft), 'sales department processes' (retail "
            "side-job, not a tech skill), 'optimise production' (furniture "
            "job). Promoted Metasploit + Secure Coding to high. Added the "
            "explicit security stack from TECHNICAL SKILLS: Burp Suite, "
            "Nmap, Penetration Testing, Vulnerability Assessment, Threat "
            "Modeling, React, Tailwind CSS."
        ),
    ),
    "real_cv8": dict(
        promote_to_high=["Software Testing"],
        move_to_fp=["use personal organization software", "communication"],
        add_gold=[
            ("CUST:playwright", "Playwright", "high"),
            ("CUST:selenium", "Selenium", "high"),
            ("CUST:langgraph", "LangGraph", "high"),
            ("CUST:llm", "LLM Integration", "high"),
            ("CUST:mcp", "MCP servers", "high"),
            ("CUST:html-css", "HTML/CSS", "high"),
            ("CUST:cpp", "C/C++", "medium"),
            ("CUST:plsql", "PL/SQL", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Angelescu Andrei-Ciprian, "
            "SWE + AI Automation Engineer. 'use personal organization "
            "software' is ESCO noise (probably triggered by Trello / Teams "
            "in tools list); 'communication' is a generic soft skill. "
            "Promoted Software Testing to high — explicit QA Engineer "
            "role. Added Playwright, Selenium, LangGraph, LLM Integration, "
            "MCP servers, HTML/CSS, C/C++, PL/SQL."
        ),
    ),
    "real_cv9": dict(
        promote_to_high=[],
        move_to_fp=["ML (computer programming)", "communication"],
        add_gold=[
            ("CUST:plsql", "PL/SQL", "high"),
            ("CUST:cpp", "C/C++", "high"),
            ("CUST:pandas", "Pandas", "high"),
            ("CUST:numpy", "NumPy", "high"),
            ("CUST:uml", "UML", "high"),
            ("CUST:sql", "SQL", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Andreea Sfetcu, Computer "
            "Science / data science. 'ML (computer programming)' is "
            "duplicate-ish with 'machine learning' and reads like a "
            "Module 2 hallucination (no language called 'ML'). "
            "'communication' is soft-skill noise. Added PL/SQL, C/C++, "
            "Pandas, NumPy, UML, SQL — all in the Programming Skills line."
        ),
    ),
    "real_cv10": dict(
        promote_to_high=[],
        move_to_fp=[],
        add_gold=[
            ("CUST:c", "C", "high"),
            ("CUST:html-css", "HTML/CSS", "high"),
            ("CUST:javascript", "JavaScript", "high"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Tobescu Andrei-Gabriel, "
            "Business Informatics student (Bitdefender product mgmt "
            "academy). Thin technical CV — Technical Skills list has just "
            "C / HTML / CSS / JavaScript / Microsoft Office. Bootstrap "
            "only captured 'use microsoft office' + 'computer science'; "
            "added the three explicit programming entries."
        ),
    ),
    "real_cv11": dict(
        promote_to_high=[
            "JavaScript",
            "Python (computer programming)",
            "OpenAI API",
        ],
        move_to_fp=[
            "give constructive feedback",
            "lead a team",
            "lead others",
            "think analytically",
        ],
        add_gold=[
            ("CUST:spring-boot", "Spring Boot", "high"),
            ("CUST:plsql", "PL/SQL", "high"),
            ("CUST:cpp", "C/C++", "high"),
            ("CUST:react", "React", "high"),
            ("CUST:deepseek-api", "DeepSeek API", "medium"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Alexandru-Vladimir Mitroi, "
            "Economic Informatics 3rd year. Cleaned soft-skill FPs from "
            "his HR director role (give constructive feedback / lead a "
            "team / lead others / think analytically). Promoted "
            "JavaScript, Python, OpenAI API — explicit in technical "
            "skills / project. Added Spring Boot, PL/SQL, C/C++, React, "
            "DeepSeek API."
        ),
    ),
    "real_cv12": dict(
        promote_to_high=[],
        move_to_fp=[
            "communication",
            "geometry",
            "logic",
            "mechanics",
            "plan",
            "dies",
            "brainstorm ideas",
            "stimulate creative processes",
            "ecosystems",
            "report facts",
            "think creatively",
        ],
        add_gold=[
            ("CUST:unity", "Unity", "high"),
            ("CUST:opengl", "OpenGL", "high"),
            ("CUST:pytorch", "PyTorch", "high"),
            ("CUST:cmake", "CMake", "high"),
            ("CUST:cpp", "C++", "high"),
            ("CUST:c", "C", "high"),
            ("CUST:assembly", "Assembly", "high"),
            ("CUST:glsl", "GLSL", "high"),
            ("CUST:react", "React", "high"),
            ("CUST:jira", "Jira", "high"),
            ("CUST:blender", "Blender", "medium"),
        ],
        notes=(
            "Reviewed 2026-05-13 against PDF. Diaconescu Andrei-Alexandru, "
            "Game / VR Developer. Massive FP cleanup — Module 2 picked up "
            "ESCO terms triggered by gamedev jargon (geometry / mechanics "
            "/ ecosystems / plan / dies / logic) plus generic soft "
            "skills (communication / brainstorm / stimulate creative / "
            "report facts / think creatively). Added the actual stack "
            "from PROGRAMMING / TOOLS / EXPERTISE: Unity, OpenGL, PyTorch, "
            "CMake, C++, C, Assembly, GLSL, React, Jira, Blender."
        ),
    ),
}


def main() -> None:
    for cv_id, plan in PLAN.items():
        path = LABELS_DIR / f"{cv_id}.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))

        gold = doc.get("gold_skills") or []
        fp = list(doc.get("skills_definitely_not_in_cv") or [])

        # 1) Promote medium -> high
        for label in plan["promote_to_high"]:
            for entry in gold:
                if entry.get("label") == label:
                    entry["confidence_expected"] = "high"

        # 2) Move FPs out
        keep, dropped = [], []
        fp_set = set(plan["move_to_fp"])
        for entry in gold:
            if entry.get("label") in fp_set:
                dropped.append(entry["label"])
            else:
                keep.append(entry)
        for label in dropped:
            if label not in fp:
                fp.append(label)

        # 3) Append new gold entries (skip if label already present)
        existing_labels = {e.get("label") for e in keep}
        for uri, label, conf in plan["add_gold"]:
            if label in existing_labels:
                continue
            keep.append(
                {
                    "skill_uri": uri,
                    "label": label,
                    "confidence_expected": conf,
                }
            )

        doc["gold_skills"] = keep
        doc["skills_definitely_not_in_cv"] = fp
        doc["notes"] = plan["notes"]

        ordered_keys = ["cv_id", "gold_skills", "skills_definitely_not_in_cv", "notes"]
        ordered = {k: doc[k] for k in ordered_keys}

        with path.open("w", encoding="utf-8") as fh:
            yaml.dump(
                ordered,
                fh,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        print(
            f"OK {cv_id}: "
            f"gold={len(keep)} fp={len(fp)} "
            f"(promoted {len(plan['promote_to_high'])}, "
            f"moved {len(dropped)}, "
            f"added {sum(1 for _, l, _ in plan['add_gold'] if l not in existing_labels)})"
        )


if __name__ == "__main__":
    main()

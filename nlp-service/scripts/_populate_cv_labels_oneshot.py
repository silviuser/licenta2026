"""One-shot script to populate gold_skills for real_cv13/14/15."""

from pathlib import Path
import yaml

LABELS_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval_corpus" / "cv_labels"


DATA = {
    "real_cv13": {
        "gold_skills": [
            ("CUST:react", "React.js", "high"),
            ("CUST:nextjs", "Next.js", "high"),
            ("CUST:react-query", "React Query", "high"),
            ("CUST:docker", "Docker", "high"),
            ("CUST:git", "Git", "high"),
            ("CUST:mysql", "MySQL", "high"),
            ("CUST:azure", "Microsoft Azure", "high"),
            ("CUST:frontend-development", "Front-End Development", "high"),
            ("CUST:javascript", "JavaScript", "medium"),
            ("CUST:agile", "Agile", "medium"),
            ("CUST:code-review", "Code Review", "medium"),
            ("CUST:3d-printing", "3D Printing", "medium"),
        ],
        "notes": (
            "Populated 2026-05-13 from PDF review. Paliciuc Cosmin - SWE Intern "
            "@Adobe (current), prior internship @METAMINDS using React.js / "
            "Next.js / React Query / Docker / Git / Agile. Top Skills (LinkedIn): "
            "Front-End Development, MySQL, Microsoft Azure. JavaScript marked "
            "medium because it is implicit via the React/Next stack rather than "
            "explicitly named."
        ),
    },
    "real_cv14": {
        "gold_skills": [
            ("CUST:java", "Java", "high"),
            ("CUST:databases", "Databases", "high"),
            ("CUST:automation", "Automation", "high"),
            ("CUST:rpa", "Robotic Process Automation (RPA)", "high"),
            ("CUST:generative-ai", "Generative AI", "high"),
            ("CUST:llm", "Large Language Models (LLMs)", "high"),
            ("CUST:rag", "RAG (Retrieval-Augmented Generation)", "high"),
            ("CUST:arduino", "Arduino", "high"),
            ("CUST:iot", "Internet of Things (IoT)", "medium"),
            ("CUST:cybersecurity", "Cybersecurity", "medium"),
            ("CUST:sql", "SQL", "medium"),
        ],
        "notes": (
            "Populated 2026-05-13 from PDF review. Diana Ovejan - 3rd-year CS "
            "student at UPB (FILS/IoT), Technical Support Intern @Adobe. Java + "
            "databases explicit in summary; Top Skills (LinkedIn): Automation, "
            "RPA, GenAI. Certs: Java 1 Associate, Introduction to Generative AI, "
            "Introduction to Automation, Building RAG Agents with LLMs. SQL / IoT "
            "/ Cybersecurity marked medium - implied via 'databases', FILS "
            "specialization and the iTEC Cybersecurity Hackathon participation "
            "rather than explicit listings."
        ),
    },
    "real_cv15": {
        "gold_skills": [
            ("CUST:cybersecurity", "Cybersecurity", "high"),
            ("CUST:soc-analyst", "SOC Analyst", "high"),
            ("CUST:siem", "SIEM", "high"),
            ("CUST:incident-response", "Security Incident Response", "high"),
            ("CUST:threat-detection", "Threat Detection", "high"),
            ("CUST:bug-bounty", "Bug Bounty", "medium"),
            ("CUST:data-visualization", "Data Visualization", "high"),
            ("CUST:pandas", "Pandas (Software)", "high"),
            ("CUST:data-manipulation", "Data Manipulation", "high"),
            ("CUST:python", "Python", "medium"),
            ("CUST:scripting", "Scripting", "medium"),
            ("CUST:programming", "Programming", "medium"),
        ],
        "notes": (
            "Populated 2026-05-13 from PDF review. Radulescu Alexandru-Gabriel - "
            "Security Engineer @Adobe (current), prior SOC Analyst @DIGI Romania "
            "(SIEM, incident triage, response). Top Skills (LinkedIn): Data "
            "Visualization, Pandas (Software), Data Manipulation. Multiple "
            "cybersecurity certs (Pre Security, Intro to Cyber Security, Advent "
            "of Cyber 2025, Practical Bug Bounty). Python / Scripting / "
            "Programming marked medium because they are implied via Pandas usage "
            "and 'automation scripts' rather than explicitly named."
        ),
    },
}


def main() -> None:
    for cv_id, spec in DATA.items():
        doc = {
            "cv_id": cv_id,
            "gold_skills": [
                {
                    "skill_uri": uri,
                    "label": label,
                    "confidence_expected": conf,
                }
                for uri, label, conf in spec["gold_skills"]
            ],
            "skills_definitely_not_in_cv": [],
            "notes": spec["notes"],
        }
        path = LABELS_DIR / f"{cv_id}.yaml"
        with path.open("w", encoding="utf-8") as fh:
            yaml.dump(
                doc,
                fh,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )
        print(f"OK {cv_id}: {len(spec['gold_skills'])} gold_skills")


if __name__ == "__main__":
    main()

"""One-shot script to update JD YAML fixtures with metadata + cleaned skill lists."""

from pathlib import Path
import yaml

JDS_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval_corpus" / "jds"


UPDATES: dict[str, dict] = {
    "jd1": dict(
        location="Bucharest",
        category="backend",
        seniority="junior",
        required_skills=[
            "Java",
            "Dependency Injection/ Inversion of Control (Spring)",
            "Unit and Mock Testing (JUnit, Mockito)",
            "Strong understanding of Design and Architectural Patterns",
            "Apache Maven",
            "GIT Repository Management",
            "Continuous Integration tools (Jenkins or similar)",
            "Basic Linux operating system knowledge",
        ],
        nice_to_have_skills=[
            "Apache Camel",
            "Enterprise Integration Patterns",
            "Java Architecture for XML Binding (JAXB)",
            "XML Transformations (XSLT, XSD, DTD)",
            "Java Message Service (JMS)",
            "Drools",
            "Agile Methodologies (SCRUM and Kanban)",
        ],
    ),
    "jd2": dict(
        location="",
        category="backend",
        seniority="junior",
        required_skills=[
            "Java",
            "Spring Boot",
            "Kafka (streams, consumer groups, message delivery guarantees)",
            "Elasticsearch (indexing, queries, performance tuning)",
            "microservices architecture, distributed systems, and REST APIs",
            "Docker, container-based deployment, and CI/CD pipelines",
            "asynchronous/event-driven systems and messaging patterns",
        ],
        nice_to_have_skills=[
            "React frontend",
            "Kubernetes",
            "Python or Node.js services within a distributed ecosystem",
            "AI/ML pipelines or data processing frameworks",
            "security best practices for distributed systems",
        ],
    ),
    "jd3": dict(
        location="Romania",
        category="swe",
        seniority="junior",
        required_skills=[
            "HTML/CSS",
            "JavaScript",
            "PHP",
            "MSSQL",
            "Linux",
            "SSL/TLS",
            "SSO",
        ],
        nice_to_have_skills=[],
    ),
    "jd4": dict(
        location="Hybrid",
        category="backend",
        seniority="unspecified",
        required_skills=[
            "Strong experience with Java 8+ and Spring Boot",
            "Solid knowledge of Git and version control best practices",
            "Familiarity with Docker or other containerization tools",
            "Cloud environment familiarity (AWS, GCP, Azure)",
            "Bonus points for experience with Golang",
        ],
        nice_to_have_skills=[
            "Proficiency in REST API design, development & integration",
            "Security best practices in backend development",
            "Solid grasp of Unit Testing and TDD",
            "Exposure to Kafka or similar messaging platforms (RabbitMQ, ActiveMQ, etc.)",
            "Understanding of CI/CD pipelines, familiarity with microservices and event-driven architecture",
        ],
    ),
    "jd5": dict(
        location="Bucharest",
        category="swe",
        seniority="unspecified",
        required_skills=[
            "Object-oriented programming (C++, preferred)",
            "Strong understanding of multithreading and concurrent programming",
            "Experience with C++ and CMake",
            "Experience in real-time embedded systems",
            "Familiarity with Linux OS",
            "Basic knowledge of web technologies",
            "Experience working on multidisciplinary products",
        ],
        nice_to_have_skills=[],
    ),
    "jd6": dict(
        location="",
        category="backend",
        seniority="unspecified",
        required_skills=[
            "Solid knowledge of Java 11 at least, Spring, relational database (PostgreSQL, Sybase), GIT, Maven",
            "Good knowledge of Java Microservices, Spring Boot, JPA, REST",
            "Java 21, Docker, Kubernetes, ELK, JavaScript with Angular or React would be a plus",
            "Good knowledge of Linux environment and Shell scripting required",
            "Hands-on experience with tools such as Eclipse/IntelliJ, Jenkins or Github Actions CI/CD Pipelines, JUnit, Jira, Cucumber",
        ],
        nice_to_have_skills=[],
    ),
    "jd7": dict(
        location="",
        category="swe",
        seniority="unspecified",
        required_skills=[
            "Experience in C/C++ for audio processing.",
            "Experience developing mobile apps for Android using audio-specific low-level libraries (OpenSLES, AAudio, Oboe), NDK (Native Development Kit), SDK (Software Development Kit), frameworks.",
            "Experience in Java for Android application integration.",
            "Experience with Android Studio and SVN, maintaining Android toolchain, build Android APK packages.",
            "Strong skills using adb, logcat, systrace, and dumpsys.",
            "Familiarity with ALSA (Advanced Linux Sound Architecture) and Android Audio Hardware Abstraction Layer (HAL).",
        ],
        nice_to_have_skills=[
            "Knowledge of networking concepts and Linux network stack programming",
            "Understanding voice communication and voice signaling concepts",
        ],
    ),
    "jd8": dict(
        location="",
        category="devops",
        seniority="mid",
        required_skills=[
            "Sound understanding of change management processes and controls in large organizations.",
            "Strong experience of envisioning and driving full stack automation in medium to large sized groups.",
            "SAP Standard Product BCS (Business Consolidation System)",
            "Financial Accounting in Banks and respective Closure Process (Month, Quarter and Year End).",
            "Driver Based Cost Management (DBCM)",
            "Basis ABAP debugging skills.",
            "Experience with Linux/Unix systems and scripting languages such as, Python and shell",
            "Automation with tools such as Ansible, SSH, and Shell",
            "Monitoring tools like Geneos, Prometheus, Grafana",
            "Networks and load balancing and ssh keys.",
            "Expertise in Unix command line and shell scripting.",
            "Incident, Problem and Change Management processes within the ITSM framework - ITIL V3 Foundation certified.",
            "Service Management tools (e.g. ServiceNow, JIRA, etc.)",
        ],
        nice_to_have_skills=[
            "Knowledge about Banking Products (on Balance Sheet, Derivatives etc.)",
            "Exposure to GCP and monitoring tools such as NewRelic",
        ],
    ),
    "jd9": dict(
        location="",
        category="devops",
        seniority="mid",
        required_skills=[
            "Administration of Java and HTTP application servers.",
            "Advanced knowledge of Windows, Linux/UNIX operating systems.",
            "Experience with databases: Oracle, SQL, RDS, PostgreSQL.",
            "Hands-on experience with cloud platforms (AWS and/or Azure).",
            "Experience with Web Services: APIs, SOAP, REST.",
            "Knowledge of integration concepts (message queues, web services, SCA, databases, etc.).",
            "Automation tools: Git, Gradle, Jenkins, Artifactory.",
            "Tools: Toad, SQL Developer, IBM Data Studio, IBM MQ Explorer, ODI, SFTP clients.",
            "Containerization and orchestration: Docker, Kubernetes, OpenShift.",
            "Familiarity with CI/CD concepts, microservices, web services, ELK stack.",
            "Ability to develop or enhance CI/CD pipelines for modern and legacy systems.",
        ],
        nice_to_have_skills=[
            "Basic understanding of Artificial Intelligence and ability to use AI tools.",
            "Issue tracking tools: Jira.",
        ],
    ),
    "jd10": dict(
        location="",
        category="backend",
        seniority="unspecified",
        required_skills=[
            "Strong experience with Python (core language + performance optimization)",
            "Solid understanding of algorithms and data structures",
            "Experience working with AWS (e.g., EC2, S3, Lambda, or similar)",
            "Hands-on experience with Ansible for automation/configuration management",
            "Familiarity with Linux environments and scripting",
            "Experience with version control systems (e.g., Git)",
        ],
        nice_to_have_skills=[],
    ),
    "jd11": dict(
        location="",
        category="qa",
        seniority="unspecified",
        required_skills=[
            "Java automated test frameworks and tools, e.g. JUnit, Cucumber",
            "Test analysis skills (ideally ISTQB qualification)",
            "API and web services knowledge (REST)",
        ],
        nice_to_have_skills=[
            "Knowledge of container technologies (Docker, Swarm)",
            "Knowledge of CI/CD processes and the corresponding tools like Maven, Git, SVN, Jenkins",
            "Practical experience in Agile frameworks (Scrum) and tools (Jira)",
            "Java application frameworks, e.g. Spring, Hibernate",
            "General Linux knowledge",
        ],
    ),
    "jd12": dict(
        location="",
        category="swe",
        seniority="senior",
        required_skills=[
            "Back-end: Java, .Net (at least one programming language should be mastered and another known)",
            "CI/CD: Git, GitLab CI",
            "Tooling: SonarQube, SAST, DAST, Intellij or VScode",
            "Cloud: Notions on Google Cloud Platform (GCP), Tanzu",
            "Infrastructure: Docker, Kubernetes (GKE), Oauth2 OIDC, SAMLv2",
            "Methodologies: Agile / Kanban",
        ],
        nice_to_have_skills=[
            "At least 5 years of experience in one backend programming language, 2+ on another one",
            "Interest in cloud-native principles and containerization",
        ],
    ),
    "jd13": dict(
        location="",
        category="data",
        seniority="unspecified",
        required_skills=[
            "Extended hands-on experience in AWS Redshift, data pipeline development, and version control systems",
            "Proficient in - Git, Airflow, DBT",
            "Basic knowledge of Python",
            "Good understanding of data warehouse architecture and cloud-based data engineering principles.",
        ],
        nice_to_have_skills=[
            "Domain knowledge of telecommunication industry",
            "SDLC and Agile methodologies",
        ],
    ),
    "jd14": dict(
        location="",
        category="data",
        seniority="junior",
        required_skills=[
            "Basic hands-on experience with Python and/or Scala",
            "Familiarity with big data technologies such as Apache Spark and workflow orchestration tools (e.g., Airflow)",
            "Understanding of cloud platforms, preferably AWS",
        ],
        nice_to_have_skills=[],
    ),
    "jd15": dict(
        location="",
        category="qa",
        seniority="unspecified",
        required_skills=[
            "QA skills - troubleshooting, bug isolation and reporting, and a solid understanding of testing methodologies and processes",
            "Experience testing across different operating systems: Android, iOS, Windows and macOS",
            "Familiarity with mobile and web testing frameworks (manual and automated).",
            "Basic networking knowledge",
            "Scripting or automation experience, preferably with Python or Java",
            "Experience with Agile workflows and issue tracking systems such as Jira",
        ],
        nice_to_have_skills=[
            "Interest or hands-on experience with AI-based testing or automation tools",
        ],
    ),
    "jd16": dict(
        location="",
        category="swe",
        seniority="junior",
        required_skills=[
            "C",
            "Assembly",
            "Cryptography",
            "Embedded software development",
            "ARM Cortex M",
            "RISC V",
        ],
        nice_to_have_skills=[
            "Post Quantum Cryptography (DES, AES, RSA, ECC, SHA)",
            "Side channel (SCA) and fault attacks (FA) countermeasures",
        ],
    ),
    "jd17": dict(
        location="",
        category="swe",
        seniority="unspecified",
        required_skills=[
            "Proficiency in C# development.",
            "Strong knowledge of HTML and JavaScript.",
            "Experience with PowerShell scripting.",
            "Familiarity with Visual Studio IDE.",
            "Basic understanding of database concepts.",
            "Exposure to Jira for task management.",
        ],
        nice_to_have_skills=[],
    ),
    "jd18": dict(
        location="",
        category="swe",
        seniority="unspecified",
        required_skills=[
            "C++",
            "Windows",
            "Linux",
            "STL",
            "BOOST",
            "CMake or Makefiles",
        ],
        nice_to_have_skills=[
            "Cross-platform build/debug skills",
            "Experience with server management utilities or datacenter tooling",
            "Familiarity with UEFI/BIOS configuration, Redfish/REST, XML/JSON parsing, and network file transfer",
            "CI/CD experience; contribution to release processes and automated testing infrastructure",
            "Experience with Electron/Node/Vue front ends or wrapping C++ CLIs with GUIs",
        ],
    ),
    "jd19": dict(
        location="",
        category="swe",
        seniority="junior",
        required_skills=[
            "Microsoft Power Platform (1+ year)",
            "RPA solutions with Power Automate Desktop",
            "Microsoft Power Platform certification (PL-900, PL-200)",
            "Agile Scrum",
        ],
        nice_to_have_skills=[
            "Other low-code and RPA platforms",
        ],
    ),
    "jd20": dict(
        location="",
        category="swe",
        seniority="unspecified",
        required_skills=[
            "Strong experience with .NET Core, C#, MVC, WebAPI, Entity Framework, and SQL",
            "Knowledge of Kubernetes, MSSQL, Redis, and cloud platforms (GCP preferred)",
            "Experience with test automation",
        ],
        nice_to_have_skills=[],
    ),
}


class _StrDumper(yaml.SafeDumper):
    pass


def _repr_str(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_StrDumper.add_representer(str, _repr_str)


def main() -> None:
    for path in sorted(JDS_DIR.glob("jd*.yaml")):
        jd_id = path.stem
        if jd_id not in UPDATES:
            print(f"SKIP {jd_id}: no update spec")
            continue
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)

        update = UPDATES[jd_id]
        doc["location"] = update["location"]
        doc["category"] = update["category"]
        doc["seniority"] = update["seniority"]
        doc["required_skills"] = update["required_skills"]
        doc["nice_to_have_skills"] = update["nice_to_have_skills"]

        ordered_keys = [
            "id",
            "title",
            "language",
            "location",
            "category",
            "seniority",
            "source_anonymized",
            "raw_text",
            "required_skills",
            "nice_to_have_skills",
            "notes",
        ]
        ordered = {k: doc[k] for k in ordered_keys if k in doc}

        with path.open("w", encoding="utf-8") as fh:
            yaml.dump(
                ordered,
                fh,
                Dumper=_StrDumper,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )
        print(f"OK   {jd_id}")


if __name__ == "__main__":
    main()

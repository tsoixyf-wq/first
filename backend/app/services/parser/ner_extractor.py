"""
NER-based entity extraction for resumes.
Uses a hybrid approach: regex patterns + GLiNER zero-shot + spaCy.

Extracts: name, email, phone, school, company, skills, dates, etc.
"""

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class NERExtractor:
    """Extract named entities from resume text using regex + NER models."""

    # --- Regex Patterns ---

    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    PHONE_PATTERN = re.compile(
        r"(?:(?:\+?86)?[-\s]?)?1[3-9]\d{9}"  # Chinese mobile
        r"|(?:\d{3,4}[-]\d{7,8})"  # Chinese landline
        r"|(?:\+\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}"  # International
    )
    URL_PATTERN = re.compile(
        r"https?://(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+(?:/[^\s]*)?"
        r"|github\.com/[a-zA-Z0-9_-]+"
        r"|linkedin\.com/in/[a-zA-Z0-9_-]+"
    )

    # Chinese name pattern (2-4 characters, common surnames)
    CHINESE_NAME_PATTERN = re.compile(
        r"(?:姓名|名字|名称)[:：\s]*([一-龥]{2,4})"
    )

    # English name pattern (First Last format, typically at resume top)
    ENGLISH_NAME_PATTERN = re.compile(
        r"(?:^name[:：\s]*|[Nn]ame[:：\s]+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        re.MULTILINE,
    )

    # Fallback: detect English name from first line (e.g., "John Smith" at top)
    ENGLISH_NAME_FALLBACK = re.compile(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*$",
        re.MULTILINE,
    )

    # English address patterns
    ENGLISH_ADDRESS_PATTERN = re.compile(
        r"(?:address|location)[:：\s]*([^\n]{5,60})",
        re.IGNORECASE,
    )

    # International phone (already covered by PHONE_PATTERN, but add US format)
    US_PHONE_PATTERN = re.compile(
        r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    )

    # Education section headers
    EDUCATION_HEADERS = [
        "教育背景", "教育经历", "学历", "学习经历",
        "education", "academic", "background", "academic background",
        "educational background", "qualifications",
    ]

    # Work experience section headers
    WORK_HEADERS = [
        "工作经历", "工作经验", "工作背景", "实习经历", "实习经验",
        "work experience", "employment", "professional experience",
        "work history", "career history", "employment history",
        "internships", "internship experience",
    ]

    # Skills section headers
    SKILL_HEADERS = [
        "专业技能", "技能", "技术能力", "技术栈", "掌握技能",
        "skills", "technical skills", "technologies",
        "core competencies", "key skills", "programming languages",
        "tools & technologies",
    ]

    # Project section headers
    PROJECT_HEADERS = [
        "项目经历", "项目经验", "项目", "个人项目",
        "projects", "personal projects", "project experience",
        "portfolio", "open source",
    ]

    # Certification section headers
    CERTIFICATION_HEADERS = [
        "证书", "资格认证", "证书与认证",
        "certifications", "certificates", "licenses",
        "professional certifications", "credentials",
    ]

    # Language section headers
    LANGUAGE_HEADERS = [
        "语言能力", "外语水平", "语言",
        "languages", "language skills", "language proficiency",
    ]

    # Common skills for fuzzy matching (Chinese + English)
    COMMON_SKILLS = [
        # Programming Languages
        "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C",
        "C#", "PHP", "Ruby", "Swift", "Kotlin", "Scala", "R", "Dart", "MATLAB", "SQL",
        "HTML", "CSS",
        # Frameworks & Libraries
        "React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt", "Django", "Flask", "FastAPI",
        "Spring Boot", "Spring", "Express", "NestJS", "Gin", "Electron",
        "PyTorch", "TensorFlow", "Keras", "Scikit-learn", "Pandas", "NumPy", "OpenCV",
        "LangChain", "LangGraph", "LlamaIndex", "Transformers",
        "Redux", "GraphQL", "gRPC", "WebSocket",
        # Databases
        "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "Kafka",
        "Cassandra", "Neo4j", "ClickHouse", "TiDB", "DynamoDB",
        # Tools & Platforms
        "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Linux", "Git",
        "RabbitMQ", "Nginx", "Jenkins", "GitHub Actions", "GitLab CI", "CI/CD",
        "Terraform", "Ansible", "Prometheus", "Grafana", "ELK",
        # Mobile
        "Flutter", "React Native", "微信小程序", "SwiftUI", "Uniapp",
        "Android", "iOS", "Taro",
        # Embedded / IoT
        "嵌入式开发", "ARM", "FPGA", "RTOS", "MQTT", "单片机", "物联网",
        # Data Engineering
        "Spark", "Flink", "Airflow", "dbt", "Snowflake", "ETL",
        "Hadoop", "Hive", "数据仓库", "数据湖",
        # AI / ML (expanded)
        "深度学习", "机器学习", "自然语言处理", "计算机视觉", "大语言模型",
        "RAG", "AI Agent", "Prompt工程", "模型微调", "模型部署",
        "数据挖掘", "推荐系统", "强化学习", "GAN", "知识图谱",
        "XGBoost", "LightGBM", "CatBoost", "MLflow",
        # Chinese skills
        "数据分析", "后端开发", "前端开发", "全栈开发",
        "微服务", "分布式", "高并发", "系统设计",
        # Academic
        "LaTeX", "SPSS", "Stata", "统计分析",
    ]

    def __init__(self):
        self._spacy_models: dict[str, object] = {}

    def _get_spacy_model(self, lang: str = "zh"):
        """Lazy-load spaCy model for given language. Falls back to zh if en unavailable."""
        if lang in self._spacy_models:
            return self._spacy_models[lang] if self._spacy_models[lang] is not False else None

        from app.services.parser.language_detector import get_spacy_model
        model_name = get_spacy_model(lang)

        try:
            import spacy
            model = spacy.load(model_name)
            self._spacy_models[lang] = model
            logger.info("spaCy model loaded", model=model_name, lang=lang)
        except Exception:
            logger.warning(
                "spaCy model not available",
                model=model_name,
                lang=lang,
            )
            # Try fallback to zh
            if lang != "zh":
                try:
                    import spacy
                    model = spacy.load("zh_core_web_sm")
                    self._spacy_models[lang] = model
                    logger.info("Fallback to zh model for", lang=lang)
                except Exception:
                    self._spacy_models[lang] = False
            else:
                self._spacy_models[lang] = False

        return self._spacy_models[lang] if self._spacy_models[lang] is not False else None

    async def extract(self, text: str) -> dict[str, Any]:
        """Extract all entities from resume text.

        Returns a dict with keys: name, email, phone, urls, schools,
        companies, skills, titles, years_of_experience
        """
        result = {
            "name": "",
            "email": "",
            "phone": "",
            "urls": [],
            "schools": [],
            "companies": [],
            "skills": [],
            "titles": [],
            "years_of_experience": None,
        }

        # Detect language for model selection
        from app.services.parser.language_detector import detect_language
        lang = detect_language(text)
        logger.info("Language detected", language=lang)

        # 1. Regex-based extraction (fast, always available)
        result["email"] = self._extract_email(text)
        result["phone"] = self._extract_phone(text) or self._extract_us_phone(text)
        result["urls"] = self._extract_urls(text)
        result["name"] = self._extract_chinese_name(text) or self._extract_english_name(text)

        # 2. Skill extraction from known vocabulary
        result["skills"] = self._extract_skills(text)

        # 3. GLiNER zero-shot NER (if available)
        gliner_result = await self._extract_with_gliner(text)
        if gliner_result:
            result = self._merge_results(result, gliner_result)

        # 4. spaCy-based extraction (if available, model selected by language)
        spacy_result = self._extract_with_spacy(text, lang)
        if spacy_result:
            result = self._merge_results(result, spacy_result)

        return result

    def _extract_email(self, text: str) -> str:
        match = self.EMAIL_PATTERN.search(text)
        return match.group(0) if match else ""

    def _extract_phone(self, text: str) -> str:
        match = self.PHONE_PATTERN.search(text)
        return match.group(0) if match else ""

    def _extract_urls(self, text: str) -> list[str]:
        return list(set(match.group(0) for match in self.URL_PATTERN.finditer(text)))

    def _extract_chinese_name(self, text: str) -> str:
        match = self.CHINESE_NAME_PATTERN.search(text)
        if match:
            return match.group(1)
        # Fallback: try to find name at the beginning of the resume
        first_line = text.strip().split("\n")[0].strip()
        if 2 <= len(first_line) <= 4 and all("一" <= c <= "鿿" for c in first_line):
            return first_line
        return ""

    def _extract_english_name(self, text: str) -> str:
        """Extract English name from resume text."""
        # Try explicit "Name:" field first
        match = self.ENGLISH_NAME_PATTERN.search(text)
        if match:
            name = match.group(1).strip()
            # Validate: should look like a name (2-3 words, each capitalized)
            parts = name.split()
            if all(p[0].isupper() for p in parts if p):
                return name

        # Fallback: first line of resume
        first_line = text.strip().split("\n")[0].strip()
        # Skip email-looking lines
        if "@" in first_line:
            return ""
        match = self.ENGLISH_NAME_FALLBACK.match(first_line)
        if match:
            name = match.group(1).strip()
            parts = name.split()
            if 2 <= len(parts) <= 3 and all(p[0].isupper() for p in parts):
                return name
        return ""

    def _extract_us_phone(self, text: str) -> str:
        """Extract US/International phone number."""
        match = self.US_PHONE_PATTERN.search(text)
        return match.group(0) if match else ""

    def _extract_skills(self, text: str) -> list[str]:
        """Extract skills by matching against a known skill vocabulary."""
        text_lower = text.lower()
        found_skills = set()
        for skill in self.COMMON_SKILLS:
            if skill.lower() in text_lower:
                found_skills.add(skill)
        return sorted(found_skills)

    async def _extract_with_gliner(self, text: str) -> dict[str, Any] | None:
        """GLiNER zero-shot NER — controlled by ENABLE_GLINER setting.

        Set ENABLE_GLINER=true in .env to enable. Defaults to off because:
        1. LLM extraction covers the same entity types with better accuracy
        2. GLiNER adds 300-500 MB of model download on first run
        3. Startup is ~2-5s slower with GLiNER loaded
        """
        from app.core.config import get_settings
        if not get_settings().ENABLE_GLINER:
            logger.debug("GLiNER skipped (ENABLE_GLINER=false)")
            return None

        try:
            from gliner import GLiNER as GLiNERModel

            if self._gliner is None:
                self._gliner = GLiNERModel.from_pretrained("urchade/gliner_medium-v2.1")
                logger.info("GLiNER model loaded")

            entities = self._gliner.predict_entities(text, labels=["person", "organization", "location", "date"])
            result: dict[str, list] = {}
            for ent in entities:
                key = {"person": "names", "organization": "companies", "location": "locations", "date": "dates"}.get(ent["label"], ent["label"] + "s")
                result.setdefault(key, []).append(ent["text"])
            return result

        except ImportError:
            logger.warning("GLiNER package not installed — run: pip install gliner")
            return None
        except Exception as e:
            logger.warning("GLiNER extraction failed: %s", e)
            return None

    def _extract_with_spacy(self, text: str, lang: str = "zh") -> dict[str, Any] | None:
        """Use spaCy for entity recognition."""
        model = self._get_spacy_model(lang)
        if model is None:
            return None

        try:
            doc = model(text[:100000])  # Truncate for performance
            result: dict[str, list] = {
                "schools": [],
                "companies": [],
                "titles_spacy": [],
            }

            for ent in doc.ents:
                if ent.label_ in ("ORG",):
                    result["companies"].append(ent.text)
                elif ent.label_ in ("PERSON",):
                    if not result.get("name"):
                        result["name"] = ent.text
                elif ent.label_ in ("GPE", "LOC"):
                    result.setdefault("locations", []).append(ent.text)

            return {k: v for k, v in result.items() if v}
        except Exception as e:
            logger.warning("spaCy extraction failed", error=str(e))
            return None

    def _merge_results(self, base: dict, new: dict) -> dict:
        """Merge two extraction results, new values supplementing base."""
        for key, value in new.items():
            if key == "name" and value and not base.get("name"):
                base["name"] = value
            elif isinstance(value, list) and isinstance(base.get(key), list):
                existing = set(str(s).lower() for s in base[key])
                for item in value:
                    if str(item).lower() not in existing:
                        base[key].append(item)
            elif value and not base.get(key):
                base[key] = value
            elif key not in base:
                base[key] = value
        return base

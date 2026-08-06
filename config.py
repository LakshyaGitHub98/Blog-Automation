import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings:
    def __init__(self):
        self.llm_provider = os.getenv("LLM_PROVIDER", "groq")
        self.llm_model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.local_base_url = os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1")
        self.local_model = os.getenv("LOCAL_MODEL", "qwen2.5:14b")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.85"))
        # comma-separated list; tried in order on failure/timeout
        self.llm_provider_priority = [
            p.strip()
            for p in os.getenv("LLM_PROVIDER_PRIORITY", "groq,nvidia").split(",")
            if p.strip()
        ]

        db_url = os.getenv("DATABASE_URL", "")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        self.database_url = (
            db_url
            or "sqlite:///" + os.path.join(BASE_DIR, "blog_gen.db").replace(os.sep, "/")
        )

        self.redis_url = os.getenv("REDIS_URL", "")

        self.detector_mode = os.getenv("DETECTOR_MODE", "mock")
        self.detector_results_path = os.getenv(
            "DETECTOR_RESULTS_PATH", os.path.join(BASE_DIR, "detector_results.json")
        )
        self.threshold = float(os.getenv("HUMANIZE_THRESHOLD", "0.6"))
        self.max_iterations = int(os.getenv("MAX_ITERATIONS", "1"))
        self.max_tokens = int(os.getenv("MAX_TOKENS", "2000"))

        self.llm_timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.llm_max_retries = int(os.getenv("LLM_MAX_RETRIES", "0"))
        self.job_stale_seconds = int(os.getenv("JOB_STALE_SECONDS", "900"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_file = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "logs", "app.log"))


settings = Settings()

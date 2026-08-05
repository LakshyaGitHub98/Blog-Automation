import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings:
    def __init__(self):
        self.llm_provider = os.getenv("LLM_PROVIDER", "nvidia")
        self.llm_model = os.getenv("LLM_MODEL", "deepseek-ai/deepseek-v4-flash")
        self.nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.local_base_url = os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1")
        self.local_model = os.getenv("LOCAL_MODEL", "qwen2.5:14b")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.85"))

        db_url = os.getenv("DATABASE_URL", "")
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
        self.max_iterations = int(os.getenv("MAX_ITERATIONS", "3"))


settings = Settings()

from config import settings
from libs.detector.colab import ColabDetector
from libs.detector.mock import MockDetector


def get_detector():
    if settings.detector_mode == "colab":
        return ColabDetector(settings.detector_results_path)
    return MockDetector()


__all__ = ["get_detector", "MockDetector", "ColabDetector"]

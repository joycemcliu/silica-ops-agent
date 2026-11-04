import pytest

from command_guard.assessment.questions import questions
from command_guard.models import Assessment
from command_guard.policy import Policy


@pytest.fixture
def policy(tmp_path):
    protected = tmp_path / "protected"
    sensitive = tmp_path / "secret"
    protected.mkdir()
    sensitive.mkdir()
    return Policy((str(protected),), (str(sensitive),))


@pytest.fixture
def safe():
    return Assessment.parse(
        {
            "model": "test-model",
            "answers": {
                name: {
                    "type": "choice",
                    "choice": "no",
                    "confidence": 1.0,
                    "probabilities": {"yes": 0.0, "no": 1.0, "unknown": 0.0},
                }
                for name in questions()
            },
        },
        questions(),
    )

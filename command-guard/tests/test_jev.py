import copy
import json
from unittest.mock import MagicMock, patch

import pytest

from command_guard.assessment.jev import Jev
from command_guard.assessment.questions import questions
from command_guard.models import Assessment, Command


def test_missing_key_is_unavailable(policy, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert Jev(policy).assess(Command("true", "/")).unavailable


def test_http_payload_and_response(policy, safe, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(safe.payload()).encode()
    opener = MagicMock()
    opener.open.return_value = response
    with patch("urllib.request.build_opener", return_value=opener):
        result = Jev(policy).assess(Command("pwd", "/"))
    assert result == safe
    request = opener.open.call_args.args[0]
    assert request.full_url == "https://api.typesafe.ai/v1/systemone"
    assert set(json.loads(request.data)["questions"]) == set(questions())
    assert "test-only" not in request.data.decode()


@pytest.mark.parametrize(
    "field,value",
    [
        ("confidence", float("nan")),
        ("confidence", 2),
        ("confidence", 0.1),
        ("choice", "maybe"),
        ("probabilities", {"yes": 0, "no": 0.2, "unknown": 0}),
    ],
)
def test_malformed_assessment_cannot_allow_execution(safe, field, value):
    response = copy.deepcopy(safe.payload())
    response["answers"]["file_changes"][field] = value
    with pytest.raises(ValueError):
        Assessment.parse(response, questions())


def test_timeout_is_unavailable(policy, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")
    with patch("urllib.request.build_opener", side_effect=TimeoutError):
        result = Jev(policy).assess(Command("pwd", "/"))
    assert result.unavailable

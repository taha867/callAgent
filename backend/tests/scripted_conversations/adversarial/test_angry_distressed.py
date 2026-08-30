"""AdversarialScenarioId.ANGRY_DISTRESSED — voice/sentiment.py::classify_sentiment's
_NEGATIVE_SENTIMENT_PATTERNS lexicon ("furious", "angry", "frustrated", ...). Pure
classifier test, same style as tests/unit/test_guard_classifier.py — the DELAY_DISSATISFACTION
safety-net-into-the-workflow path is already covered by test_demo_6_delayed_claim_dissatisfied.py.
"""

import pytest

from src.voice.sentiment import classify_sentiment

_ANGRY_UTTERANCES = [
    "This is absolutely unacceptable, I'm furious",
    "I'm so frustrated with this whole process",
    "أنا غاضب جدا من هذه الخدمة",
]


@pytest.mark.parametrize("utterance", _ANGRY_UTTERANCES)
def test_classifies_angry_distressed_utterances_as_negative(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "NEGATIVE"


def test_a_calm_benign_question_is_neutral():
    result = classify_sentiment("Can you tell me the status of my claim?")
    assert result.sentiment == "NEUTRAL"

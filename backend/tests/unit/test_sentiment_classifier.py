"""voice/sentiment.py — spec §18. Table-driven over each of the 4 lexicon-detectable
signals (EN + AR) plus a benign-utterance false-positive guard, mirroring
tests/unit/test_guard_classifier.py's own structure and discipline.
"""

import pytest

from src.voice.sentiment import classify_sentiment

_DELAY_DISSATISFACTION_UTTERANCES = [
    "This is ridiculous, I've been waiting two weeks for an update.",
    "Why is this taking so long?",
    "لماذا يستغرق هذا وقتا طويلا",
]

_SERVICE_FAILURE_UTTERANCES = [
    "Nobody called me back after three attempts.",
    "This service is terrible, no one is helping me.",
    "الخدمة سيئة",
]

_CUSTOMER_DISPUTE_UTTERANCES = [
    "That's not true, I already submitted the document.",
    "That's incorrect, I don't agree with that status.",
]

_NEGATIVE_SENTIMENT_UTTERANCES = [
    "This is unacceptable, I'm furious about this.",
    "I'm really frustrated with this whole process.",
    "أنا غاضب من هذا",
]

_POSITIVE_UTTERANCES = [
    "Thank you so much, that's really helpful.",
    "Perfect, I appreciate it.",
    "شكرا جزيلا",
]

_BENIGN_NEUTRAL_UTTERANCES = [
    "What's the status of my claim?",
    "When will my car be ready?",
    "Can I speak to a human agent please?",
    "My birthday is March 1990.",
    "Can you check the garage contact details for me?",
]


@pytest.mark.parametrize("utterance", _DELAY_DISSATISFACTION_UTTERANCES)
def test_classifies_delay_dissatisfaction(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "NEGATIVE"
    assert result.signal == "DELAY_DISSATISFACTION"


@pytest.mark.parametrize("utterance", _SERVICE_FAILURE_UTTERANCES)
def test_classifies_service_failure(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "NEGATIVE"
    assert result.signal == "SERVICE_FAILURE"


@pytest.mark.parametrize("utterance", _CUSTOMER_DISPUTE_UTTERANCES)
def test_classifies_customer_dispute(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "NEGATIVE"
    assert result.signal == "CUSTOMER_DISPUTE"


@pytest.mark.parametrize("utterance", _NEGATIVE_SENTIMENT_UTTERANCES)
def test_classifies_generic_negative_sentiment(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "NEGATIVE"
    assert result.signal == "NEGATIVE_SENTIMENT"


@pytest.mark.parametrize("utterance", _POSITIVE_UTTERANCES)
def test_classifies_positive_sentiment(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "POSITIVE"
    assert result.signal is None


@pytest.mark.parametrize("utterance", _BENIGN_NEUTRAL_UTTERANCES)
def test_no_false_positive_on_benign_claim_questions(utterance):
    result = classify_sentiment(utterance)
    assert result.sentiment == "NEUTRAL"
    assert result.signal is None


def test_never_raises_on_empty_or_odd_input():
    assert classify_sentiment("").sentiment == "NEUTRAL"
    assert classify_sentiment("   ").sentiment == "NEUTRAL"


def test_is_case_insensitive():
    result = classify_sentiment("THIS IS RIDICULOUS AND UNACCEPTABLE")
    assert result.sentiment == "NEGATIVE"

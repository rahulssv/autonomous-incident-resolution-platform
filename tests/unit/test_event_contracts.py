import json

from airp.core.config import Settings
from airp.messaging.contracts import RawAlertEvent
from airp.messaging.eventhub_kafka import publish_json
from airp.workers.alert_consumer import AlertConsumerWorker


class FakeProducer:
    def __init__(self) -> None:
        self.produced = []
        self.polls = []

    def produce(self, topic, key=None, value=None):
        self.produced.append({"topic": topic, "key": key, "value": value})

    def poll(self, timeout):
        self.polls.append(timeout)


class FakeMessage:
    def topic(self):
        return "airp.alerts.raw"

    def partition(self):
        return 0

    def offset(self):
        return 42

    def key(self):
        return b"alert-key"

    def value(self):
        return b"{not-json"


def test_publish_json_serializes_pydantic_event() -> None:
    producer = FakeProducer()
    event = RawAlertEvent(service="checkout-api", payload={"alerts": []})

    publish_json(producer, topic="airp.alerts.raw", key="k1", value=event)

    assert producer.produced[0]["topic"] == "airp.alerts.raw"
    assert producer.produced[0]["key"] == "k1"
    payload = json.loads(producer.produced[0]["value"].decode("utf-8"))
    assert payload["event_type"] == "airp.alert.raw"
    assert payload["service"] == "checkout-api"
    assert producer.polls == [0]


def test_alert_consumer_publishes_deadletter_event() -> None:
    producer = FakeProducer()
    worker = object.__new__(AlertConsumerWorker)
    worker.settings = Settings(kafka_deadletter_topic="airp.deadletter")
    worker.producer = producer

    worker._publish_deadletter(FakeMessage(), ValueError("Kafka message value is not valid JSON"))

    produced = producer.produced[0]
    payload = json.loads(produced["value"].decode("utf-8"))
    assert produced["topic"] == "airp.deadletter"
    assert produced["key"] == "alert-key"
    assert payload["event_type"] == "airp.deadletter"
    assert payload["error"] == "Kafka message value is not valid JSON"
    assert payload["failed_event"]["offset"] == 42

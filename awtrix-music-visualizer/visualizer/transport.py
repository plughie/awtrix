"""Transports for pushing frames to AWTRIX (HTTP and MQTT)."""

from __future__ import annotations

import json
from typing import Protocol

import requests

from .config import Config


class Transport(Protocol):
    def send(self, payload: dict) -> None: ...
    def switch_app(self, name: str) -> None: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...


class HttpTransport:
    def __init__(self, cfg: Config):
        self.url = f"http://{cfg.device.ip}/api/custom"
        self._switch_url = f"http://{cfg.device.ip}/api/switch"
        self.params = {"name": cfg.device.app_name}
        self._session = requests.Session()
        # Pre-warm the keep-alive connection.
        try:
            self._session.get(f"http://{cfg.device.ip}/api/stats", timeout=2)
        except requests.RequestException:
            pass

    def send(self, payload: dict) -> None:
        try:
            self._session.post(
                self.url,
                params=self.params,
                data=json.dumps(payload, separators=(",", ":")),
                headers={"Content-Type": "application/json"},
                timeout=0.3,
            )
        except requests.RequestException:
            pass

    def switch_app(self, name: str) -> None:
        try:
            self._session.post(
                self._switch_url, json={"name": name}, timeout=1.0
            )
        except requests.RequestException:
            pass

    def clear(self) -> None:
        try:
            self._session.post(self.url, params=self.params, data="", timeout=1.0)
        except requests.RequestException:
            pass

    def close(self) -> None:
        self._session.close()


class MqttTransport:
    def __init__(self, cfg: Config):
        import paho.mqtt.client as mqtt

        self._prefix = cfg.mqtt.prefix
        self.topic = f"{cfg.mqtt.prefix}/custom/{cfg.device.app_name}"
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="awtrix-visualizer"
        )
        if cfg.mqtt.username:
            self._client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password)
        self._client.connect(cfg.mqtt.host, cfg.mqtt.port, keepalive=30)
        self._client.loop_start()

    def send(self, payload: dict) -> None:
        self._client.publish(self.topic, json.dumps(payload, separators=(",", ":")), qos=0)

    def switch_app(self, name: str) -> None:
        self._client.publish(
            f"{self._prefix}/switch", json.dumps({"name": name}), qos=0
        )

    def clear(self) -> None:
        self._client.publish(self.topic, "", qos=0)

    def close(self) -> None:
        self.clear()
        self._client.loop_stop()
        self._client.disconnect()


def make_transport(cfg: Config) -> Transport:
    if cfg.device.transport.lower() == "mqtt":
        return MqttTransport(cfg)
    return HttpTransport(cfg)

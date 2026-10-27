"""Tests against a fake dingz.

The response payloads are minimal fixtures shaped after the TypedDicts in api.py,
not captures from a real device.
"""

import copy

import pytest
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.dingz.const import CONF_BASE_URL, DOMAIN

BASE = "http://192.0.2.10/api/v1"
MAC = "aa:bb:cc:dd:ee:ff"
DINGZ_ID = "aabbccddeeff"

STATE = {
    "dimmers": [{"on": True, "output": 50, "index": {"relative": 0, "absolute": 0}}],
    "led": {"on": False, "hsv": "0;0;100", "rgb": "FFFFFF", "mode": "hsv"},
    "sensors": {
        "brightness": 100,
        "light_state": "day",
        "room_temperature": 21.0,
        "pirs": [{"enabled": False, "motion": False}, None],
        "power_outputs": [{"value": 12}],
    },
    "thermostat": {
        "active": True,
        "enabled": True,
        "mode": "heating",
        "state": "heating",
        "target_temp": 21,
        "min_target_temp": 5,
        "max_target_temp": 30,
        "temp": 20.5,
    },
    "wifi": {"mac": MAC},
    "time": "2026-10-27 10:00:00",
}


def _device(fw_version: str) -> dict:
    return {
        MAC.replace(":", "").upper(): {
            "fw_version": fw_version,
            "hw_version": "1.0",
            "puck_hw_model": "dz1f-4b",
            "has_pir": True,
        }
    }


def _mock_dingz(aioclient_mock: AiohttpClientMocker, fw_version: str) -> None:
    aioclient_mock.get(f"{BASE}/state", json=copy.deepcopy(STATE))
    aioclient_mock.get(f"{BASE}/device", json=_device(fw_version))
    aioclient_mock.get(
        f"{BASE}/system_config",
        json={"dingz_name": "Salon", "room_name": "Salon", "id": DINGZ_ID},
    )
    aioclient_mock.get(f"{BASE}/services_config", json={"mqtt": {"enable": True}})
    aioclient_mock.get(f"{BASE}/button_config", json={"buttons": []})
    aioclient_mock.get(f"{BASE}/ddi_channels_config", status=404)
    aioclient_mock.get(f"{BASE}/input_config", json={"inputs": []})
    aioclient_mock.get(
        f"{BASE}/output_config",
        json={"outputs": [{"active": True, "name": "Plafond", "type": "light"}]},
    )
    aioclient_mock.get(f"{BASE}/blind_config", json={"blinds": []})
    aioclient_mock.get(f"{BASE}/ram", json={"free": 50000, "largest_free_block": 9000})
    aioclient_mock.post(f"{BASE}/pir/0/on", text="")
    aioclient_mock.post(f"{BASE}/pir/0/off", text="")
    aioclient_mock.post(f"{BASE}/thermostat/on", text="")
    aioclient_mock.post(f"{BASE}/thermostat/off", text="")
    aioclient_mock.post(f"{BASE}/thermostat/mode/heating", text="")
    aioclient_mock.post(f"{BASE}/thermostat/mode/cooling", text="")
    aioclient_mock.post(f"{BASE}/thermostat", text="")
    aioclient_mock.post(f"{BASE}/thermostat_config", text="")


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BASE_URL: "http://192.0.2.10"}, unique_id=MAC
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _posts(aioclient_mock: AiohttpClientMocker) -> list[str]:
    return [
        str(url) for method, url, _, _ in aioclient_mock.mock_calls if method == "POST"
    ]


def _entity_id(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr("custom_components.dingz.helpers.asyncio.sleep", _no_sleep)


async def test_pir_switch_firmware_v2(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mqtt_mock
) -> None:
    _mock_dingz(aioclient_mock, "2.1.58")
    await _setup(hass)

    switch = _entity_id(hass, "switch", f"{MAC}-pir_enable-0")
    assert hass.states.get(switch).state == "off"
    # the disabled PIR still gets a motion sensor so it can be used once enabled
    _entity_id(hass, "binary_sensor", f"{MAC}-motion-0")

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    assert f"{BASE}/pir/0/on" in _posts(aioclient_mock)

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: switch}, blocking=True
    )
    assert f"{BASE}/pir/0/off" in _posts(aioclient_mock)


async def test_no_pir_switch_firmware_v1(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mqtt_mock
) -> None:
    _mock_dingz(aioclient_mock, "1.4.3")
    await _setup(hass)

    registry = er.async_get(hass)
    assert registry.async_get_entity_id("switch", DOMAIN, f"{MAC}-pir_enable-0") is None
    assert (
        registry.async_get_entity_id("binary_sensor", DOMAIN, f"{MAC}-motion-0") is None
    )


async def test_thermostat_firmware_v2(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mqtt_mock
) -> None:
    _mock_dingz(aioclient_mock, "2.1.58")
    await _setup(hass)
    climate = _entity_id(hass, "climate", MAC)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {ATTR_ENTITY_ID: climate, ATTR_TEMPERATURE: 22},
        blocking=True,
    )
    assert f"{BASE}/thermostat?target_temp=22.0" in _posts(aioclient_mock)

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: climate, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )
    posts = _posts(aioclient_mock)
    assert f"{BASE}/thermostat/mode/cooling" in posts
    assert f"{BASE}/thermostat/on" in posts

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: climate, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    assert f"{BASE}/thermostat/off" in _posts(aioclient_mock)
    assert f"{BASE}/thermostat_config" not in _posts(aioclient_mock)


async def test_thermostat_firmware_v1_uses_config(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mqtt_mock
) -> None:
    _mock_dingz(aioclient_mock, "1.4.3")
    await _setup(hass)
    climate = _entity_id(hass, "climate", MAC)

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: climate, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    posts = _posts(aioclient_mock)
    assert f"{BASE}/thermostat_config" in posts
    assert f"{BASE}/thermostat/off" not in posts


async def test_power_live_update_over_mqtt(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mqtt_mock
) -> None:
    _mock_dingz(aioclient_mock, "2.1.58")
    await _setup(hass)
    power = _entity_id(hass, "sensor", f"{MAC}-output-power-0")
    assert hass.states.get(power).state == "12"

    async_fire_mqtt_message(hass, f"dingz/{DINGZ_ID}/dz1f-4b/power/light/0", "42.5")
    await hass.async_block_till_done()
    assert hass.states.get(power).state == "42.5"

    # a power message for another output must not change this sensor
    async_fire_mqtt_message(hass, f"dingz/{DINGZ_ID}/dz1f-4b/power/light/1", "7")
    await hass.async_block_till_done()
    assert hass.states.get(power).state == "42.5"


async def test_led_mqtt_triggers_refresh(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mqtt_mock
) -> None:
    _mock_dingz(aioclient_mock, "2.1.58")
    await _setup(hass)

    def state_calls() -> int:
        return sum(
            1
            for method, url, _, _ in aioclient_mock.mock_calls
            if method == "GET" and str(url) == f"{BASE}/state"
        )

    before = state_calls()
    async_fire_mqtt_message(
        hass, f"dingz/{DINGZ_ID}/dz1f-4b/state/led", '{"on":1,"r":255,"g":0,"b":0}'
    )
    await hass.async_block_till_done()
    assert state_calls() > before

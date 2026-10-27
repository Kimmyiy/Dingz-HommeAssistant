import contextlib
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt

from .const import DOMAIN
from .helpers import (
    CoordinatedNotificationStateEntity,
    UserAssignedNameMixin,
    compile_json_path,
    json_path_lookup,
)
from .shared import (
    DiagnosticCoordinator,
    InternalNotification,
    OutputPowerNotification,
    Shared,
    SimpleSensorStateNotification,
    StateCoordinator,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = [
        Brightness(shared),
        JsonPathSensor(
            shared.state,
            SensorEntityDescription(
                key="sensors.light_state",
                device_class=SensorDeviceClass.ENUM,
                options=["day", "night", "twilight"],
                translation_key="light_state",
            ),
        ),
        JsonPathSensor(
            shared.state,
            SensorEntityDescription(
                key="time",
                device_class=SensorDeviceClass.TIMESTAMP,
                translation_key="state_time",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
            transform_fn=_dt_with_hass_tz,
        ),
        JsonPathSensor(
            shared.state,
            SensorEntityDescription(
                key="config.timestamp",
                device_class=SensorDeviceClass.TIMESTAMP,
                translation_key="config_timestamp",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
            transform_fn=lambda raw: dt.utc_from_timestamp(raw),
        ),
        JsonPathSensor(
            shared.diag,
            SensorEntityDescription(
                key="free",
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                translation_key="diag_free",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
        ),
        JsonPathSensor(
            shared.diag,
            SensorEntityDescription(
                key="largest_free_block",
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                translation_key="diag_largest_free_block",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=False,
            ),
        ),
    ]

    try:
        dyn_light_enabled = shared.config.data.system["dyn_light"]["enable"]
    except LookupError:
        dyn_light_enabled = False

    if dyn_light_enabled:
        entities.append(
            JsonPathSensor(
                shared.state,
                SensorEntityDescription(
                    key="dyn_light.mode",
                    device_class=SensorDeviceClass.ENUM,
                    options=["day", "night", "twilight"],
                    translation_key="dyn_light",
                ),
            )
        )

    for name, is_diag in (
        ("room_temperature", False),
        ("uncompensated_temperature", True),
        ("cpu_temperature", True),
        ("puck_temperature", True),
        ("fet_temperature", True),
    ):
        entities.append(
            JsonPathSensor(
                shared.state,
                SensorEntityDescription(
                    key=f"sensors.{name}",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement="°C",
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC if is_diag else None,
                    translation_key=name,
                ),
            )
        )

    for index, dingz_output in enumerate(shared.config.data.outputs):
        if dingz_output.get("active", False):
            power = OutputPower(shared, index=index)
            entities.append(power)

    async_add_entities(entities)


def _dt_with_hass_tz(s: str) -> datetime | None:
    parsed = dt.parse_datetime(s)
    if parsed is None:
        return None
    return dt.as_utc(parsed)


class OutputPower(
    CoordinatedNotificationStateEntity, UserAssignedNameMixin, SensorEntity
):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "output_power"

    def __init__(self, shared: Shared, *, index: int) -> None:
        super().__init__(shared)
        self.__index = index
        self.__power: float | None = None

        self._attr_unique_id = (
            f"{self.coordinator.shared.mac_addr}-output-power-{index}"
        )
        self._attr_device_info = self.coordinator.shared.device_info
        self.handle_state_update()

    @property
    def comp_index(self) -> int:
        return self.__index

    @property
    def user_given_name(self) -> str | None:
        try:
            return self.coordinator.shared.config.data.outputs[self.__index].get("name")
        except LookupError:
            return None

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        # live updates from the MQTT topic 'power/light/<n>'
        if not (
            isinstance(notification, OutputPowerNotification)
            and notification.index == self.__index
        ):
            return
        self.__power = notification.value
        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        with contextlib.suppress(LookupError):
            power_outputs = self.coordinator.data["sensors"]["power_outputs"]
            self.__power = power_outputs[self.__index].get("value")

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.__power


class JsonPathSensor(
    CoordinatorEntity[StateCoordinator | DiagnosticCoordinator], SensorEntity
):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StateCoordinator | DiagnosticCoordinator,
        desc: SensorEntityDescription,
        *,
        transform_fn: Callable[[Any], StateType | date | datetime | Decimal]
        | None = None,
    ) -> None:
        super().__init__(coordinator)

        self._attr_unique_id = f"{self.coordinator.shared.mac_addr}-{desc.key}"
        self._attr_device_info = self.coordinator.shared.device_info
        self.entity_description = desc

        self.__path = compile_json_path(desc.key)
        self.__transform_fn = transform_fn

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        value = json_path_lookup(self.coordinator.data, self.__path)
        if value is None:
            return None
        if self.__transform_fn:
            return self.__transform_fn(value)
        return value


class Brightness(CoordinatedNotificationStateEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "lx"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "brightness"

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared)
        self.__brightness: float | None = None

        self._attr_unique_id = f"{self.coordinator.shared.mac_addr}-sensors.brightness"
        self._attr_device_info = self.coordinator.shared.device_info

    @callback
    def handle_notification(self, notification: InternalNotification) -> None:
        if not (
            isinstance(notification, SimpleSensorStateNotification)
            and notification.sensor == "light"
        ):
            return
        self.__brightness = notification.value
        self.async_write_ha_state()

    @callback
    def handle_state_update(self) -> None:
        with contextlib.suppress(LookupError):
            self.__brightness = self.coordinator.data["sensors"]["brightness"]

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.__brightness

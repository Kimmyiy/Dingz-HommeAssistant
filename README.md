# Dingz Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz/docs/faq/custom_repositories)
[![License](https://img.shields.io/github/license/Kimmyiy/Dingz-HommeAssistant.svg?style=flat-square)](LICENSE)

_Integration to integrate with [Dingz](https://www.dingz.ch) devices._

> [!NOTE]
> This project is based on [siku2/hass-dingz](https://github.com/siku2/hass-dingz) by Simon Berger (MIT license).
> It extends it with features from the official dingz firmware 2.0 REST API and MQTT documentation published by iolo AG.
> Don't install both integrations at the same time: they use the same `dingz` domain.

## Installation

Make sure you have [HACS](https://hacs.xyz) installed.

1. Add this repository as a custom repository to HACS: [![Add Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Kimmyiy&repository=Dingz-HommeAssistant&category=integration)
2. Use HACS to install the integration.
3. Restart Home Assistant.
4. Set up the integration using the UI: [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=dingz)
5. **(optional but recommended)** Set up the MQTT connection from dingz to Home Assistant. [Read the Guide][MQTT Guide]

## Supported Features

When you make changes to the dingz configuration (for instance when setting up the MQTT connection, or changing the output configuration), reload the integration (or restart Home Assistant) to update the entities.

The following features are fully supported and, since I'm actively using them, should always work:

- Light outputs (including dimmers)
- Front panel LED with RGB support
- PIR Motion detection (incl. live updates when used in combination with MQTT[^1])
- Button press events (**only** when used in combination with MQTT[^1])
- Power sensors for outputs
- Various other sensors like brightness, temperature etc.
- Physical dingz inputs (incl. live updates when used in combination with MQTT[^1])

The following features have been implemented, but since I'm not actively using these configurations, I don't know how well they work.

- Blinds / Motors (incl. live updates when used in combination with MQTT[^1])
- Thermostats (exposed as climate entites in Home Assistant)
- Fan outputs

> [!NOTE]
> If you're using one of these, be sure to contact me (open an issue or a new discussion). With a bit of help, I can easily improve the integration.
> This also applies to unimplemented features, of course.

And now for the list of things that **won't** be implemented:

- Dingz firmware updates through Home Assistant. As far as I can tell the dingz doesn't know itself, whether an update is available. They are performed by the mobile app by downloading the firmware blob from somewhere. I'm not planning on reverse engineering this at the moment. Don't hesitate to let me know if you have more information about this though.

[^1]: See the [MQTT Guide].

## Contributions are welcome

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

### Providing translations for other languages

Translations live in [custom_components/dingz/translations/](./custom_components/dingz/translations/). Add or edit a file there and open a pull request with the changes.

<!--  -->

[MQTT Guide]: docs/mqtt.md

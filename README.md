# Schluter DITRA-HEAT-E-RS1 for Home Assistant

This custom integration connects the **Schluter DITRA-HEAT-E-RS1** thermostat to
[Home Assistant](https://www.home-assistant.io/) through your Schluter account.
It communicates with the Schluter cloud service, so Home Assistant needs internet
access.

Only the DITRA-HEAT-E-RS1 (model 740) is currently supported. This
integration does not support other Sinopé, Ouellet, or Flextherm products, nor
other Schluter device models.

## Features

- Climate entity with heat, auto, and off modes.
- Thermostat presets, temperature controls, and device attributes such as floor
  temperature, heating demand, and alarms.
- Hourly and daily energy values on the thermostat entity, plus a daily energy
  sensor.
- Coordinated cloud polling.

## Requirements

- A Schluter account with a DITRA-HEAT-E-RS1 thermostat added to it.
- Home Assistant with internet access.

## Installation

Install the integration from HACS if available in your HACS store. Otherwise,
add this repository (`ClayKaiser/sinope-schluter`) to HACS as a custom
integration repository and install **Schluter DITRA-HEAT-E-RS1**. In Home
Assistant, the integration is listed as **Schluter DITRA-HEAT-E-RS1**.

For manual installation, copy `custom_components/sinope_schluter` from this repository
into the `custom_components` directory in your Home Assistant configuration
directory. The resulting path should be:

```text
<config>/custom_components/sinope_schluter/
```

Restart Home Assistant after installation.

## Setup

1. In Home Assistant, go to **Settings → Devices & services → Add integration**.
2. Select **Schluter DITRA-HEAT-E-RS1**.
3. Enter your Schluter account email and password.

If your credentials expire or change, Home Assistant will prompt you to
reauthenticate from the integration page.

The integration checks all locations in your account and adds every DITRA-HEAT-E-RS1
thermostat it finds. Other devices and locations without a supported thermostat are
ignored.

YAML setup is not supported. If upgrading from the former `neviweb` integration
or the previous custom `schluter` domain, remove its config entry and old
integration folder, install this integration as
`custom_components/sinope_schluter`, then add it again through the UI. Enter
your account credentials again. Existing entity IDs, automations, and service
calls may need to be updated because the integration domain changed.

## Entities and services

The integration creates a thermostat climate entity and a daily energy sensor
for each supported thermostat. Hourly and daily energy values are available as
`hourly_kwh` and `daily_kwh` attributes on the thermostat entity. The daily
total is calculated from hourly readings; the integration does not make a
separate daily-energy API request.

Thermostat-specific services are available under the `sinope_schluter` service
domain:

- `set_activation`
- `set_air_floor_mode`
- `set_aux_cycle_length`
- `set_backlight`
- `set_climate_keypad_lock`
- `set_cycle_length`
- `set_early_start`
- `set_eco_status`
- `set_em_heat`
- `set_second_display`
- `set_setpoint_max`
- `set_setpoint_min`
- `set_temperature_format`
- `set_time_format`

Use Home Assistant's **Developer tools → Actions** to view each action's input
fields and call it.

## Logging and troubleshooting

The integration uses Home Assistant's standard logging. Check the Home Assistant
logs for errors, and include relevant entries when
[opening an issue](https://github.com/ClayKaiser/sinope-schluter/issues).

To enable debug logging, add the following to your Home Assistant logger
configuration:

```yaml
logger:
  logs:
    custom_components.sinope_schluter: debug
```

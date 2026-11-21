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
- Home Assistant 2026.11.0 or newer with internet access.

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

The email must be the account's sign-in email, and the password must be the
current Schluter account password. The integration does not offer configuration
options after setup.

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

The climate entity supports off, heat, and auto modes, target temperatures, and
none, away, eco, and temporary-bypass presets. The sensor reports daily energy
in kWh. Floor temperature, heating demand, alarms, and device settings are
available as climate entity attributes.

Use the standard climate actions for everyday control:

```yaml
action: climate.set_temperature
target:
  entity_id: climate.your_thermostat
data:
  temperature: 20
```

Thermostat-specific actions are available under the `sinope_schluter` domain.
They target the thermostat climate entity and accept:

- `set_activation`: `active` (`true`/`false`).
- `set_air_floor_mode`: `airFloorMode` (`airByFloor`/`floor`).
- `set_aux_cycle_length` and `set_cycle_length`: `value` (one of `15 sec`,
  `5 min`, `10 min`, `15 min`, `20 min`, `25 min`, or `30 min`).
- `set_backlight`: `backlightIntensityIdle` (0–100).
- `set_climate_keypad_lock`: `lockKeypad` (`locked`/`unlocked`).
- `set_early_start`: `earlyStart` (`on`/`off`).
- `set_eco_status`: `status` (0/1).
- `set_em_heat`: `value` (`on`/`off`).
- `set_second_display`: `secondaryDisplay` (`outsideTemperature`/`default`).
- `set_setpoint_max` and `set_setpoint_min`: `roomSetpointMax` and
  `roomSetpointMin`, respectively.
- `set_temperature_format`: `temperatureFormat` (`celsius`/`fahrenheit`).
- `set_time_format`: `timeFormat` (12/24).

For example:

```yaml
action: sinope_schluter.set_backlight
target:
  entity_id: climate.your_thermostat
data:
  backlightIntensityIdle: 50
```

Use Home Assistant's **Developer tools → Actions** to view each action's input
fields and call it.

The integration does not provide custom conditions or triggers.

## Data updates and limitations

Thermostat attributes are polled every five minutes. Energy history is refreshed
every 30 minutes, and the account's device inventory is checked hourly. These
intervals are fixed. The integration requires the Schluter cloud service and
does not communicate locally with thermostats. A newly added supported
thermostat appears after the next inventory refresh.

Only model 740 is supported. Energy data depends on hourly history being
available from Schluter; there may be a delay before the current hour is
reported. The daily total uses UTC midnight as its reset boundary.

## Use cases

- Set room temperature and switch between automatic scheduling, manual heat,
  and off from Home Assistant.
- Use away and eco presets when the home is unoccupied or energy use should be
  reduced.
- Track the thermostat's daily energy total alongside other Home Assistant
  energy data.
- Automate device settings such as the idle backlight or keypad lock with the
  integration actions.

## Troubleshooting

- **Authentication error:** Confirm the account email and password by signing in
  to Schluter, then reauthenticate the integration in Home Assistant.
- **Thermostat unavailable:** Check that the thermostat is online and the
  Schluter cloud service is reachable. The entity returns when polling succeeds.
- **Energy is missing or delayed:** Allow time for Schluter to publish its
  hourly reading; history refreshes every 30 minutes.
- **A new thermostat is missing:** Confirm it is model 740 and allow up to one
  hour for the next inventory check.
- **An action fails:** Confirm the device is online and the action's field value
  is within the accepted values listed above, then check the Home Assistant
  logs.

## Removal

In Home Assistant, remove the **Schluter DITRA-HEAT-E-RS1** config entry from
**Settings → Devices & services**. To uninstall the integration, remove it in
HACS or delete `custom_components/sinope_schluter` if installed manually, then
restart Home Assistant.

## Logging

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

## Development

Install the test dependencies with `python -m pip install -r requirements_test.txt`,
then run:

```shell
pytest tests
coverage run --source=custom_components.sinope_schluter -m pytest tests
coverage report -m
mypy
```

The tests use Home Assistant's custom integration fixtures and do not require a
Schluter account. Mypy uses strict mode for the integration package.

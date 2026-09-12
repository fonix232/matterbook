"""Config and options flow for MatterBook."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_ALLOW_TRIALS,
    CONF_APPLY_METADATA,
    CONF_AUTO_PAIR,
    CONF_MAX_ATTEMPTS,
    CONF_PAIR_ON_ADD,
    CONF_PAIR_TIMEOUT,
    CONF_REQUIRE_EXACT_MATCH,
    CONF_RETRY_COOLDOWN,
    CONF_SCAN_INTERVAL,
    CONF_USE_BLUETOOTH,
    DEFAULT_ALLOW_TRIALS,
    DEFAULT_APPLY_METADATA,
    DEFAULT_AUTO_PAIR,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_PAIR_ON_ADD,
    DEFAULT_PAIR_TIMEOUT,
    DEFAULT_REQUIRE_EXACT_MATCH,
    DEFAULT_RETRY_COOLDOWN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_BLUETOOTH,
    DOMAIN,
)


def _seconds(minimum: int, maximum: int) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
        )
    )


class MatterBookConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the MatterBook config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and create the entry.

        There is nothing to ask: the book and its images live in one fixed
        directory under the configuration folder, and everything else is an
        option that can be changed later.
        """
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="MatterBook", data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> MatterBookOptionsFlow:
        """Return the options flow."""
        return MatterBookOptionsFlow()


class MatterBookOptionsFlow(OptionsFlow):
    """Handle MatterBook options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): _seconds(30, 86400),
                    vol.Required(
                        CONF_AUTO_PAIR, default=options.get(CONF_AUTO_PAIR, DEFAULT_AUTO_PAIR)
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_ALLOW_TRIALS,
                        default=options.get(CONF_ALLOW_TRIALS, DEFAULT_ALLOW_TRIALS),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_PAIR_ON_ADD,
                        default=options.get(CONF_PAIR_ON_ADD, DEFAULT_PAIR_ON_ADD),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_REQUIRE_EXACT_MATCH,
                        default=options.get(
                            CONF_REQUIRE_EXACT_MATCH, DEFAULT_REQUIRE_EXACT_MATCH
                        ),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_USE_BLUETOOTH,
                        default=options.get(CONF_USE_BLUETOOTH, DEFAULT_USE_BLUETOOTH),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_APPLY_METADATA,
                        default=options.get(CONF_APPLY_METADATA, DEFAULT_APPLY_METADATA),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_PAIR_TIMEOUT,
                        default=options.get(CONF_PAIR_TIMEOUT, DEFAULT_PAIR_TIMEOUT),
                    ): _seconds(30, 900),
                    vol.Required(
                        CONF_MAX_ATTEMPTS,
                        default=options.get(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=10, step=1, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Required(
                        CONF_RETRY_COOLDOWN,
                        default=options.get(CONF_RETRY_COOLDOWN, DEFAULT_RETRY_COOLDOWN),
                    ): _seconds(60, 86400),
                }
            ),
        )

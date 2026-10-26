"""Config flow for Hopla integration."""
from typing import Any
import logging
import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector, SelectSelectorConfig, SelectSelectorMode,
    TextSelector, TextSelectorConfig, TextSelectorType,
)

from .const import (DOMAIN, CONF_URL, CONF_TOKEN, CONF_SHOW_DUE_IN, CONF_SHOW_NO_DUE_DATE,
                    CONF_CREATE_UNIFIED_LIST, CONF_CREATE_ASSIGNEE_LISTS, CONF_PARENT_USERS, CONF_PARENT_PIN,
                    CONF_PARENT_PIN_HASH, CONF_PARENT_PIN_SALT)
from .api import HoplaApiClient
from .parental import hash_pin, valid_pin

_LOGGER = logging.getLogger(__name__)

class HoplaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hopla."""

    VERSION = 1
    
    def __init__(self):
        """Initialize the config flow."""
        self._server_data = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                client = HoplaApiClient(
                    user_input[CONF_URL],
                    user_input[CONF_TOKEN],
                    session,
                )
                # Test the API connection
                await client.async_get_tasks()

                # Store server data and proceed to options step  
                self._server_data = user_input
                return await self.async_step_options()
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL): str,
                vol.Required(CONF_TOKEN): str,
            }),
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the options step."""
        if user_input is not None:
            final_data = {
                **self._server_data,
                CONF_SHOW_DUE_IN: user_input.get(CONF_SHOW_DUE_IN, 7),
                CONF_SHOW_NO_DUE_DATE: user_input.get(CONF_SHOW_NO_DUE_DATE, True),
                CONF_CREATE_UNIFIED_LIST: user_input.get(CONF_CREATE_UNIFIED_LIST, True),
                CONF_CREATE_ASSIGNEE_LISTS: user_input.get(CONF_CREATE_ASSIGNEE_LISTS, False),
            }
            
            return self.async_create_entry(
                title="Hopla",
                data=final_data
            )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema({
                vol.Optional(CONF_SHOW_DUE_IN, default=7): vol.Coerce(int),
                vol.Optional(CONF_SHOW_NO_DUE_DATE, default=True): bool,
                vol.Optional(CONF_CREATE_UNIFIED_LIST, default=True): bool,
                vol.Optional(CONF_CREATE_ASSIGNEE_LISTS, default=False): bool,
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return HoplaOptionsFlowHandler(config_entry)

class HoplaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Hopla options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}
        pin = (user_input or {}).get(CONF_PARENT_PIN) or ""
        if pin and not valid_pin(pin):
            errors[CONF_PARENT_PIN] = "invalid_pin"
        if user_input is not None and not errors:
            # A blank code keeps the current one; only its hash is stored.
            pin_hash, pin_salt = hash_pin(pin) if pin else (
                self.entry.data.get(CONF_PARENT_PIN_HASH), self.entry.data.get(CONF_PARENT_PIN_SALT))
            data = {
                CONF_PARENT_USERS: user_input.get(CONF_PARENT_USERS, []),
                CONF_PARENT_PIN_HASH: pin_hash,
                CONF_PARENT_PIN_SALT: pin_salt,
                CONF_URL: self.entry.data.get(CONF_URL),
                CONF_TOKEN: self.entry.data.get(CONF_TOKEN),
                CONF_SHOW_DUE_IN: user_input.get(CONF_SHOW_DUE_IN, 7),
                CONF_SHOW_NO_DUE_DATE: user_input.get(CONF_SHOW_NO_DUE_DATE, True),
                CONF_CREATE_UNIFIED_LIST: user_input.get(CONF_CREATE_UNIFIED_LIST, True),
                CONF_CREATE_ASSIGNEE_LISTS: user_input.get(CONF_CREATE_ASSIGNEE_LISTS, False),
            }

            # Workaround to being able to use the same parameters in both config and options flow. 
            # https://community.home-assistant.io/t/configflowhandler-and-optionsflowhandler-managing-the-same-parameter/365582
            self.hass.config_entries.async_update_entry(
                self.entry, data=data, options=self.entry.options
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.entry.entry_id)
            )
            self.async_abort(reason="configuration updated")
            return self.async_create_entry(title="", data={})

        users = [user for user in await self.hass.auth.async_get_users()
                 if user.is_active and not user.system_generated]
        user_options = [{"value": user.id, "label": user.name or user.id} for user in users]

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_PARENT_USERS,
                    default=self.entry.data.get(CONF_PARENT_USERS, []),
                ): SelectSelector(SelectSelectorConfig(
                    options=user_options, multiple=True, mode=SelectSelectorMode.LIST)),
                vol.Optional(CONF_PARENT_PIN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Optional(
                    CONF_SHOW_DUE_IN,
                    default=self.entry.data.get(CONF_SHOW_DUE_IN, 7)
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_SHOW_NO_DUE_DATE,
                    default=self.entry.data.get(CONF_SHOW_NO_DUE_DATE, True)
                ): bool,
                vol.Optional(
                    CONF_CREATE_UNIFIED_LIST,
                    default=self.entry.data.get(CONF_CREATE_UNIFIED_LIST, True)
                ): bool,
                vol.Optional(
                    CONF_CREATE_ASSIGNEE_LISTS,
                    default=self.entry.data.get(CONF_CREATE_ASSIGNEE_LISTS, False)
                ): bool,
            }),
        )
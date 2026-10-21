"""Constants for the Hopla integration."""
DOMAIN = "hopla"
TODO_STORAGE_KEY = f"{DOMAIN}_items"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SHOW_DUE_IN = "show_due_in"
CONF_SHOW_NO_DUE_DATE = "show_no_due_date"
CONF_CREATE_UNIFIED_LIST = "create_unified_list"
CONF_CREATE_PROJECT_LISTS = "create_project_lists"
CONF_CREATE_ASSIGNEE_LISTS = "create_assignee_lists"

# Live updates make polling a safety net: rare while connected, frequent while not.
LIVE_REFRESH_INTERVAL = 1800  # seconds
OFFLINE_REFRESH_INTERVAL = 300  # seconds

API_TIMEOUT = 10  # seconds
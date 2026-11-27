"""Constants for the Hopla integration."""
DOMAIN = "hopla"
TODO_STORAGE_KEY = f"{DOMAIN}_items"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SHOW_DUE_IN = "show_due_in"
CONF_SHOW_NO_DUE_DATE = "show_no_due_date"
CONF_CREATE_UNIFIED_LIST = "create_unified_list"
CONF_CREATE_ASSIGNEE_LISTS = "create_assignee_lists"
# Minutes before a routine, a moment or a task starts or ends at which Hopla fires an event, e.g. "10,5".
CONF_NOTICE_MINUTES = "notice_minutes"
# The morning briefing: its time ("07:30", empty = off) and whose tasks it lists
# (user ids and "none" for the tasks of nobody; empty = everybody).
CONF_BRIEFING_TIME = "briefing_time"
CONF_BRIEFING_MEMBERS = "briefing_members"
# Home Assistant users who may approve, edit and spend points, and the hashed
# four-digit code that opens parent mode on a shared tablet.
CONF_PARENT_USERS = "parent_users"
CONF_PARENT_PIN = "parent_pin"
CONF_PARENT_PIN_HASH = "parent_pin_hash"
CONF_PARENT_PIN_SALT = "parent_pin_salt"

# Live updates make polling a safety net: rare while connected, frequent while not.
LIVE_REFRESH_INTERVAL = 1800  # seconds
OFFLINE_REFRESH_INTERVAL = 300  # seconds

API_TIMEOUT = 10  # seconds
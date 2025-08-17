"""Nautobot development configuration file."""

# pylint: disable=invalid-envvar-default
import os
import sys

from nautobot.core.settings import *  # noqa: F403  # pylint: disable=wildcard-import,unused-wildcard-import
from nautobot.core.settings_funcs import is_truthy, parse_redis_connection

#
# Debug
#

DEBUG = is_truthy(os.getenv("NAUTOBOT_DEBUG", False))

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

#
# Logging
#

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

#
# Redis
#

# Redis Cacheops
CACHEOPS_REDIS = parse_redis_connection(redis_database=1)

#
# Celery settings are not defined here because they can be overloaded with
# environment variables. By default they use `CACHES["default"]["LOCATION"]`.
#

# Enable installed plugins. Add the name of each plugin to the list.
# PLUGINS = ["nautobot_example_plugin"]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS = [
    "nautobot_data_validation_engine",
    "nautobot_chatops",
]

import os  # make sure this is at the top if not already present

PLUGINS = [
    "nautobot_data_validation_engine",
#    "nautobot_chatops",
    "nautobot_plugin_nornir",
]

PLUGINS_CONFIG = {
#    "nautobot_chatops": {
#        # Enable Grafana integration
#        "enable_grafana": True,
#
#        # These values will come from environment variables
#        "grafana_url": os.environ.get("GRAFANA_URL", ""),
#        "grafana_api_key": os.environ.get("GRAFANA_API_KEY", ""),
#
#        # Grafana defaults
#        "grafana_default_width": 0,
#        "grafana_default_height": 0,
#        "grafana_default_theme": "dark",
#        "grafana_default_timespan": "0",
#        "grafana_org_id": 1,
#        "grafana_default_tz": "America/Denver",
#    },
    "nautobot_plugin_nornir": {
        "use_config_context": {"secrets": False, "connection_options": True},
        # Optionally set global connection options.
        "connection_options": {
            "napalm": {
                "extras": {
                    "optional_args": {"global_delay_factor": 1},
                },
            },
            "netmiko": {
                "extras": {
                    "global_delay_factor": 1,
                },
            },
        },
        "nornir_settings": {
            "credentials": "nautobot_plugin_nornir.plugins.credentials.env_vars.CredentialsEnvVars",
            "runner": {
                "plugin": "threaded",
                "options": {
                    "num_workers": 20,
                },
            },
        },
    }
}

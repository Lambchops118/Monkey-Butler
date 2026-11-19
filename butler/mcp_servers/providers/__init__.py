from .world_context import register as register_world_context_tools
from .discord_messages import register as register_discord_message_tools
from .device_information import register as register_device_information_tools
from .home_automation import register as register_home_automation_tools
from .sleep_mode import register as register_sleep_mode_tools
from .smart_plugs import register as register_smart_plug_tools
from .tv_control import register as register_tv_control_tools

__all__ = [
    "register_world_context_tools",
    "register_device_information_tools",
    "register_discord_message_tools",
    "register_home_automation_tools",
    "register_sleep_mode_tools",
    "register_smart_plug_tools",
    "register_tv_control_tools",
]

__version__ = "0.2.0"
default_app_config = "pretix_waitlist_manager.apps.PluginApp"

try:
    from .apps import PluginApp

    PretixPluginMeta = PluginApp.PretixPluginMeta
except Exception:  # pragma: no cover
    PretixPluginMeta = None

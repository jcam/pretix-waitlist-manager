from django.utils.translation import gettext_lazy as _

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:  # pragma: no cover
    raise RuntimeError("Please use a recent pretix version to run this plugin!")


class PluginApp(PluginConfig):
    """Register the waitlist-manager plugin with pretix."""

    default = True
    name = "pretix_waitlist_manager"
    verbose_name = "Waitlist Manager"

    class PretixPluginMeta:
        """Expose pretix plugin metadata used in discovery and compatibility checks."""

        name = _("Waitlist Manager")
        author = "Jesse"
        description = _(
            "Manage waitlists with membership imports and randomized ordering"
        )
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2025.11.0"

    def ready(self):
        """Patch pretix navigation when Django loads the plugin.

        Args:
            None.
        Returns:
            `None`. The pretix event navigation is patched in place.
        """
        from .navigation import patch_event_navigation

        patch_event_navigation()

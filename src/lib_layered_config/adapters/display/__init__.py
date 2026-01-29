"""Display adapters for rendering configuration output.

Provide Rich-styled and plain text rendering of configuration data with
provenance information. The display module is the presentation layer's
interface for configuration visualization.

Contents:
    * :func:`display_config` - Main API for configuration display with Rich styling.

System Role:
    Presentation adapters consume ``Config`` objects and render them to
    the console. They honour the same provenance metadata as CLI helpers
    but apply Rich styling for enhanced readability.
"""

from .rich import display_config

__all__ = ["display_config"]

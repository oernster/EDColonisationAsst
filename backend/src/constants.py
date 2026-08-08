"""Values shared across layers that must have exactly one definition.

Deliberately free of imports. Everything else in the backend depends on
configuration or logging, both of which depend on each other, so a constant
that lives anywhere else cannot be read by all of its consumers: putting the
backend port in utils/ made config import utils, which imports the logger,
which imports config. The whole package then stopped loading.
"""

from __future__ import annotations

# The port the application asks for, written down once.
#
# Deliberately an unusual one. Every other development server reaches first for
# 8000, 8080, 5000, 3000 or 8888, which makes those the ports most likely to be
# taken already on a real machine; they are also the ones an operating system
# reserves. 8000 fell inside a Windows reservation covering 7949 to 9056 and
# could not be bound at all, while nothing whatsoever was listening on it.
#
# 47021 sits in the registered range rather than the ephemeral one, so a port
# the operating system hands out cannot land on it either. It remains a
# preference and not a guarantee; utils.ports resolves what is actually used.
DEFAULT_BACKEND_PORT = 47021

# Tried in order when the preferred port cannot be bound, before falling back
# to whatever the operating system will give. A short list of known addresses
# is worth more than a random one: the web UI keeps a predictable address that
# a bookmark or a tablet on the LAN can still reach. All of these were checked
# against a machine whose reservations covered 7949 to 9056, 49711 to 49910
# and 50000 to 50559, so none of them sits in a range Windows commonly takes.
BACKEND_PORT_CANDIDATES = (
    DEFAULT_BACKEND_PORT,
    46617,
    45219,
    44317,
    43391,
    41573,
    39207,
    37421,
)

__all__ = ["BACKEND_PORT_CANDIDATES", "DEFAULT_BACKEND_PORT"]

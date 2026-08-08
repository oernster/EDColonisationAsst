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

__all__ = ["DEFAULT_BACKEND_PORT"]

"""System tracker service - tracks current player system"""

from abc import ABC, abstractmethod

from ..models.journal_events import DockedEvent, FSDJumpEvent, LocationEvent
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ISystemTracker(ABC):
    """Interface for system tracking"""

    @abstractmethod
    def get_current_system(self) -> str | None:  # pragma: no cover
        """Get the current system name"""

    @abstractmethod
    def update_from_location(self, event: LocationEvent) -> None:  # pragma: no cover
        """Update current system from Location event"""

    @abstractmethod
    def update_from_jump(self, event: FSDJumpEvent) -> None:  # pragma: no cover
        """Update current system from FSDJump event"""

    @abstractmethod
    def update_from_docked(self, event: DockedEvent) -> None:  # pragma: no cover
        """Update current system from Docked event"""


class SystemTracker(ISystemTracker):
    """
    Tracks the player's current star system.
    Follows Single Responsibility Principle.
    """

    def __init__(self) -> None:
        self._current_system: str | None = None
        self._current_station: str | None = None
        self._is_docked: bool = False

    def get_current_system(self) -> str | None:
        """
        Get the current system name

        Returns:
            Current system name or None if unknown
        """
        return self._current_system

    def get_current_station(self) -> str | None:
        """
        Get the current station name if docked

        Returns:
            Current station name or None if not docked
        """
        return self._current_station if self._is_docked else None

    def is_docked(self) -> bool:
        """
        Check if player is currently docked

        Returns:
            True if docked, False otherwise
        """
        return self._is_docked

    def update_from_location(self, event: LocationEvent) -> None:
        """
        Update current system from Location event

        Args:
            event: Location event from journal
        """
        old_system = self._current_system
        self._current_system = event.star_system
        self._is_docked = event.docked
        self._current_station = event.station_name if event.docked else None

        if old_system != self._current_system:
            logger.info(f"System changed: {old_system} -> {self._current_system}")

        if self._is_docked:
            logger.info(f"Docked at {self._current_station} in {self._current_system}")

    def update_from_jump(self, event: FSDJumpEvent) -> None:
        """
        Update current system from FSDJump event

        Args:
            event: FSDJump event from journal
        """
        old_system = self._current_system
        self._current_system = event.star_system
        self._is_docked = False
        self._current_station = None

        logger.info(
            f"Jumped to {self._current_system} "
            f"(from {old_system}, distance: {event.jump_dist:.2f} LY)"
        )

    def update_from_docked(self, event: DockedEvent) -> None:
        """
        Update current system from Docked event

        Args:
            event: Docked event from journal
        """
        self._current_system = event.star_system
        self._current_station = event.station_name
        self._is_docked = True

        logger.info(f"Docked at {self._current_station} in {self._current_system}")

"""
Base Collector Abstract Class.

All data collectors inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseCollector(ABC):
    """
    Abstract base class for data collectors.

    Subclasses must implement:
    - collector_type: Unique identifier for this collector
    - collect(): Method to gather and return data
    """

    @property
    @abstractmethod
    def collector_type(self) -> str:
        """Return the unique type identifier for this collector."""
        pass

    @abstractmethod
    def collect(self) -> Optional[Dict[str, Any]]:
        """
        Collect data and return as dictionary.

        Returns:
            Dict containing collected data, or None if no data available
        """
        pass

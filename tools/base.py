from abc import ABC, abstractmethod
from typing import Dict, Any


class Tool(ABC):
    """Base class for all tools that can be used by the LLM."""

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return the tool schema in Anthropic's format.

        Returns:
            Dict containing:
                - type: Tool type (e.g., "custom", "bash_20250124")
                - name: Tool name
                - description: Tool description
                - input_schema: JSON schema for tool inputs
        """
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Tool-specific result
        """
        pass

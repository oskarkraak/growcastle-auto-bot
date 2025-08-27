"""
Modular captcha solver interface for Grow Castle bot.

This module provides a base interface for captcha solvers and implements
a solver chain that tries multiple solving strategies in order.
"""

import random
from abc import ABC, abstractmethod
from typing import Optional


class CaptchaSolver(ABC):
    """Base interface for captcha solvers."""
    
    @abstractmethod
    def solve_captcha(self, folder_name: str, screenshot_count: int) -> Optional[int]:
        """
        Solve captcha and return the log index (0-based).
        
        Args:
            folder_name: Path to folder containing captcha screenshots
            screenshot_count: Number of screenshots in the folder
            
        Returns:
            Log index (0-7) if solved successfully, None if failed
        """
        pass

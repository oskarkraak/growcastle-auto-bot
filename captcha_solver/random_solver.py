"""
Random captcha solver implementation.

This is a fallback solver that randomly selects a log when other methods fail.
"""

import random
from typing import Optional
from .captcha_solver import CaptchaSolver


NUM_LOGS = 8  # Total number of logs to choose from


class RandomSolver(CaptchaSolver):
    """Fallback solver that randomly selects a log."""
    
    def solve_captcha(self, folder_name: str, screenshot_count: int) -> Optional[int]:
        return random.randint(0, NUM_LOGS - 1)

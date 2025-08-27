"""
Captcha solver chain implementation.

This module provides a chain of captcha solvers that tries multiple strategies 
in order until one succeeds.
"""

from captcha_solver import tilt_based_solver, movement_based_solver, random_solver
from .captcha_solver import CaptchaSolver


class ChainedCaptchaSolver(CaptchaSolver):
    """
    Chain of captcha solvers that tries multiple strategies in order.
    
    Attempts to solve captcha using multiple solvers in sequence until one succeeds.
    """

    def __init__(self):
        self.solvers = [
            movement_based_solver.MovementBasedSolver(),
            tilt_based_solver.TiltBasedSolver(),
            random_solver.RandomSolver()
        ]

    def solve_captcha(self, folder_name: str, screenshot_count: int) -> int:
        for solver in self.solvers:
            result = solver.solve_captcha(folder_name, screenshot_count)
            if result is None:
                print(f"{solver.name} failed to solve captcha")
            else:
                print(f"Captcha solved by {solver.name}: log {result}")
                return result

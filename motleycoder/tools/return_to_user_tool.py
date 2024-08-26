from typing import Callable, Optional

from motleycrew.agents import MotleyOutputHandler
from motleycrew.common import Defaults
from motleycrew.common.exceptions import InvalidOutput

from motleycoder.user_interface import UserInterface


class ReturnToUserTool(MotleyOutputHandler):
    _name = "return_to_user"

    def __init__(
        self,
        user_interface: UserInterface,
        tests_runner: Optional[Callable] = None,
        max_iterations: int = Defaults.DEFAULT_OUTPUT_HANDLER_MAX_ITERATIONS,
    ):
        self.user_interface = user_interface
        self.tests_runner = tests_runner
        super().__init__(max_iterations=max_iterations)

        self._iteration = 0

    def handle_output(self):
        self._iteration += 1

        out = self.tests_runner()
        if out is None:
            self._iteration = 0
            return "Tests passed!"
        elif self._iteration >= self.max_iterations:
            self._iteration = 0
            return "Maximum output handler iterations exceeded. Last test attempt failed:\n" + out
        else:
            if self.user_interface.confirm("Attempt to fix test errors?"):
                raise InvalidOutput("Existing tests failed:\n" + out)
            return "Last test attempt failed:\n" + out

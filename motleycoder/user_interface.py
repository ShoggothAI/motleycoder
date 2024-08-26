from motleycrew.common import logger

class UserInterface:
    def __init__(self, yes: bool = False):
        self.yes = yes

    def confirm(self, message: str) -> bool:
        if self.yes:
            approved = True
        else:
            approved = input(f"{message} [y/n] ").lower().startswith("y")

        logger.info(f"{message} {"approved" if approved else "rejected"}")
        return approved

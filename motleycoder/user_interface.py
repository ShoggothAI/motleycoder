class UserInterface:
    def __init__(self, yes: bool = False):
        self.yes = yes

    def confirm(self, message: str) -> bool:
        if self.yes:
            return True
        return input(f"{message} [y/n] ").lower().startswith("y")

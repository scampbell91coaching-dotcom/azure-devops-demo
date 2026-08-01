from ..repositories.status_repository import JsonStatusRepository


class PlatformStatusService:
    def __init__(self, repository=None):
        self.repository = repository or JsonStatusRepository()

    def get_status(self):
        return self.repository.load()

    def checks_for(self, *areas):
        allowed = set(areas)
        return [
            c for c in self.get_status().get("checks", []) if c.get("area") in allowed
        ]

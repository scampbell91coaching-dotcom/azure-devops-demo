import json, os
from pathlib import Path
class JsonStatusRepository:
    def __init__(self, path=None):
        default = Path(__file__).resolve().parents[2] / "data" / "platform-status.json"
        self.path = Path(path or os.getenv("PLATFORM_STATUS_FILE", default))
    def load(self):
        if not self.path.exists():
            return {"score":0,"summary":{"pass":0,"warn":0,"fail":1},"checks":[{"area":"Portal","name":"Status data","status":"FAIL","detail":f"Missing {self.path}"}]}
        try:
            with self.path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return {"score":0,"summary":{"pass":0,"warn":0,"fail":1},"checks":[{"area":"Portal","name":"Status data","status":"FAIL","detail":f"Unable to read status data: {exc}"}]}

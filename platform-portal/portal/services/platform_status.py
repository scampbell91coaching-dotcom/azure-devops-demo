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

    def observability_status(self):
        """Return a stable observability contract from one repository read.

        Missing values remain UNKNOWN rather than being coerced to a healthy or
        unhealthy boolean.  A repository-level failure is retained as a control
        so the UI can explain why telemetry is unavailable.
        """
        data = self.get_status()
        if not isinstance(data, dict):
            data = {}
        observability = data.get("observability")
        availability = data.get("availability")
        observability = observability if isinstance(observability, dict) else {}
        availability = availability if isinstance(availability, dict) else {}

        metrics = self._boolean_dependency(
            observability, "metrics_api_available", false_status="UNAVAILABLE"
        )
        service_monitor = self._boolean_dependency(
            observability,
            "service_monitor_present",
            false_status="NOT_CONFIGURED",
        )

        http_code = availability.get("http_code")
        if http_code is None or isinstance(http_code, (dict, list)):
            health = {"status": "UNKNOWN", "http_code": None}
        else:
            code = str(http_code)
            health = {
                "status": "AVAILABLE" if code == "200" else "UNAVAILABLE",
                "http_code": code,
            }

        latency = availability.get("health_latency_seconds")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            latency_sample = {"status": "UNKNOWN", "seconds": None}
        elif latency < 0:
            latency_sample = {"status": "UNKNOWN", "seconds": None}
        else:
            latency_sample = {
                "status": (
                    "AVAILABLE" if health["status"] == "AVAILABLE" else "DEGRADED"
                ),
                "seconds": latency,
            }

        raw_checks = data.get("checks")
        controls = []
        if isinstance(raw_checks, list):
            for check in raw_checks:
                if not isinstance(check, dict):
                    continue
                area = check.get("area")
                if area not in {"Observability", "Availability", "Performance"}:
                    # Keep repository failures visible instead of returning an
                    # inexplicably empty controls table.
                    if not (area == "Portal" and check.get("name") == "Status data"):
                        continue
                controls.append(
                    {
                        "area": self._display_text(area),
                        "name": self._display_text(check.get("name")),
                        "status": self._control_status(check.get("status")),
                        "detail": self._display_text(check.get("detail")),
                    }
                )

        return {
            "generated_at": data.get("generated_at"),
            "telemetry": {
                "metrics_api": metrics,
                "service_monitor": service_monitor,
                "health": health,
                "latency_sample": latency_sample,
            },
            "controls": controls,
        }

    @staticmethod
    def _boolean_dependency(source, key, false_status):
        value = source.get(key)
        if value is True:
            status = "AVAILABLE"
        elif value is False:
            status = false_status
        else:
            status = "UNKNOWN"
            value = None
        return {"status": status, "value": value}

    @staticmethod
    def _control_status(value):
        value = str(value).upper() if value is not None else "UNKNOWN"
        return value if value in {"PASS", "WARN", "FAIL"} else "UNKNOWN"

    @staticmethod
    def _display_text(value):
        if value is None or isinstance(value, (dict, list)):
            return "Not reported"
        return str(value)

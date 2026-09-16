import json
from datetime import UTC, datetime

from runtime_support import launch_core, stop_core

process, ready, token, runtime = launch_core()
print(
    json.dumps(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "INFO",
            "component": "dev_launcher",
            "event": "core_endpoint",
            "endpoint": ready["endpoint"],
        }
    )
)
try:
    process.wait()
except KeyboardInterrupt:
    pass
finally:
    stop_core(process, ready, token, runtime)

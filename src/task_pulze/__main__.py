import logging
import sys

from pydantic import ValidationError

from task_pulze.config import get_settings
from task_pulze.logging_config import configure_logging
from task_pulze.server import create_server


def main() -> None:
    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"task-pulze: invalid configuration\n{exc}", file=sys.stderr)
        sys.exit(2)

    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    try:
        server = create_server(settings)
    except Exception as exc:
        logger.error("Could not initialise storage: %s", exc)
        sys.exit(1)
    logger.info("Starting task-pulze at %s/mcp", settings.base_url)
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()

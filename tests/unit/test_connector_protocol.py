import asyncio

import pytest

from astrolens.connectors.base import ArchiveConnector
from astrolens.core.enums import SourceHealthStatus
from astrolens.core.errors import UnsupportedConnectorOperation
from astrolens.core.models import SourceHealth


class MinimalConnector(ArchiveConnector):
    name = "minimal"

    async def healthcheck(self) -> SourceHealth:
        return SourceHealth(name=self.name, status=SourceHealthStatus.OK)


def test_default_unsupported_connector_operation_is_typed() -> None:
    connector = MinimalConnector()

    with pytest.raises(UnsupportedConnectorOperation) as exc_info:
        asyncio.run(connector.resolve_object("M87"))

    assert exc_info.value.code == "UNSUPPORTED_CONNECTOR_OPERATION"
    assert exc_info.value.details == {"connector": "minimal", "operation": "resolve_object"}

import pytest
from pydantic import TypeAdapter

from src.gofile_uploader.types import GetServersResponse


@pytest.mark.skip(reason="Gofile /servers endpoint is deprecated")
class TestAPIServers:
    @pytest.mark.asyncio(scope="session")
    async def test_get_servers(self, base_cli_config_api):
        api = base_cli_config_api
        response = api.get_servers()
        response_validator = TypeAdapter(GetServersResponse)
        response_validator.validate_python(response, strict=True)

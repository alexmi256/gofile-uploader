import pytest
from pydantic import TypeAdapter

from src.gofile_uploader.types import GetServersResponse


class TestAPIServers:
    @pytest.mark.asyncio(scope="session")
    async def test_get_servers_old(self, base_cli_config_api):
        api = base_cli_config_api
        response = await api.get_servers_old(None)
        response_validator = TypeAdapter(GetServersResponse)
        response_validator.validate_python(response, strict=True)

    @pytest.mark.asyncio(scope="session")
    async def test_get_servers_na_old(self, base_cli_config_api):
        api = base_cli_config_api
        region = "na"
        response = await api.get_servers_old(region)
        response_validator = TypeAdapter(GetServersResponse)
        response_validator.validate_python(response, strict=True)
        servers_with_undesired_regions = [x["zone"] for x in response["data"]["servers"] if x["zone"] != region]
        assert servers_with_undesired_regions == []

    @pytest.mark.asyncio(scope="session")
    async def test_get_servers(self, base_cli_config_api):
        api = base_cli_config_api
        response = api.get_servers(None)
        response_validator = TypeAdapter(GetServersResponse)
        response_validator.validate_python(response, strict=True)

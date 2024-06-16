from copy import deepcopy

import pytest
import pytest_asyncio
from pydantic import TypeAdapter

from src.gofile_uploader.api import GofileIOAPI
from src.gofile_uploader.types import (
    GetAccountDetailsResponse,
    GetAccountIdResponse,
    GetNewAccountResponse,
)


@pytest_asyncio.fixture(scope="function")
async def base_cli_config_api_no_token(base_cli_config):
    config = deepcopy(base_cli_config)

    api = GofileIOAPI(config)
    yield api
    if not api.session.closed:
        await api.session.close()


class TestAPIAccount:
    @pytest.mark.asyncio(scope="function")
    async def test_init_api_with_no_token(self, base_cli_config_api_no_token):
        api = base_cli_config_api_no_token
        assert not api.options["token"]
        await api.init()
        assert api.options["token"]
        assert api.account_id

    @pytest.mark.asyncio(scope="session")
    async def test_get_new_account(self, base_cli_config_api):
        api = base_cli_config_api
        response = await api.get_new_account()
        response_validator = TypeAdapter(GetNewAccountResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_get_account_id(self, base_cli_config_api_with_account):
        api = base_cli_config_api_with_account
        response = await api.get_account_id()
        response_validator = TypeAdapter(GetAccountIdResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_get_account_details(self, base_cli_config_api_with_account):
        api = base_cli_config_api_with_account

        account_id_response = await api.get_account_id()

        response = await api.get_account_details(account_id_response["data"]["id"])
        response_validator = TypeAdapter(GetAccountDetailsResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

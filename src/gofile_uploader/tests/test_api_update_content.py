from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from src.gofile_uploader.types import UpdateContentResponse


class TestAPIUpdateContent:
    @pytest.mark.asyncio(scope="session")
    async def test_update_folder_rename(self, folder_from_account, base_cli_config_api_with_account_initialized):
        api = base_cli_config_api_with_account_initialized

        new_folder_name = uuid4()
        content_id = folder_from_account["id"]
        response = await api.update_content(content_id, "name", new_folder_name)
        response_validator = TypeAdapter(UpdateContentResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    @pytest.mark.parametrize("is_public", ["true", "false"])
    async def test_update_folder_make_public(
        self, folder_from_account, base_cli_config_api_with_account_initialized, is_public
    ):
        api = base_cli_config_api_with_account_initialized

        content_id = folder_from_account["id"]
        response = await api.update_content(content_id, "public", is_public)
        response_validator = TypeAdapter(UpdateContentResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.parametrize("content_option", ["password", "description", "tags"])
    @pytest.mark.asyncio(scope="session")
    async def test_update_folder_set_password(
        self, folder_from_account, base_cli_config_api_with_account_initialized, content_option
    ):
        api = base_cli_config_api_with_account_initialized

        content_id = folder_from_account["id"]
        # I'm being lazy and setting content value to the same things as the option
        response = await api.update_content(content_id, content_option, content_option)
        response_validator = TypeAdapter(UpdateContentResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_update_folder_set_expiry(self, folder_from_account, base_cli_config_api_with_account_initialized):
        api = base_cli_config_api_with_account_initialized
        expiry_date = int((datetime.today() + timedelta(days=1)).timestamp())

        content_id = folder_from_account["id"]
        response = await api.update_content(content_id, "expiry", expiry_date)
        response_validator = TypeAdapter(UpdateContentResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

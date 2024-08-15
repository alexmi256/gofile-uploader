from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from src.gofile_uploader.types import CreateFolderResponse, UpdateContentResponse


class TestAPIFolder:
    @pytest.mark.asyncio(scope="session")
    async def test_create_folder(self, base_cli_config_api_with_account_initialized):
        api = base_cli_config_api_with_account_initialized

        folder_name = uuid4()

        response = await api.create_folder(api.root_folder_id, folder_name)
        response_validator = TypeAdapter(CreateFolderResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_delete_folder(self, base_cli_config_api_with_account_initialized):
        api = base_cli_config_api_with_account_initialized

        folder_name = uuid4()

        response = await api.create_folder(api.root_folder_id, folder_name)
        response_validator = TypeAdapter(CreateFolderResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)
        delete_response = await api.delete_contents([response["data"]["id"]])

        response_validator_delete = TypeAdapter(UpdateContentResponse)
        response_validator_delete.validate_python(delete_response, strict=True, from_attributes=True)

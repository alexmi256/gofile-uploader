from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from src.gofile_uploader.types import GetContentResponse


class TestAPIGetContent:
    @pytest.mark.asyncio(scope="session")
    async def test_get_folder_contents(
        self, file_in_folder, folder_from_account, base_cli_config_api_with_account_initialized
    ):
        api = base_cli_config_api_with_account_initialized
        file = file_in_folder
        folder = folder_from_account

        response = await api.get_content(file["parentFolder"], None, None)

        response_validator = TypeAdapter(GetContentResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)
        assert response["data"]["name"] == folder["name"]
        assert response["data"]["parentFolder"] == api.root_folder_id
        assert response["data"]["type"] == "folder"
        assert response["data"]["public"] is False
        assert file["id"] in response["data"]["children"]
        assert response["data"]["children"][file["id"]]["name"] == file["name"]
        assert response["data"]["children"][file["id"]]["md5"] == file["md5"]

    @pytest.mark.asyncio(scope="session")
    async def test_get_root_folder_contents(
        self, file_in_folder, folder_from_account, base_cli_config_api_with_account_initialized
    ):
        api = base_cli_config_api_with_account_initialized
        _file = file_in_folder
        _folder = folder_from_account

        response = await api.get_content(api.root_folder_id, None, None)

        assert response["data"]["isRoot"]

    @pytest.mark.asyncio(scope="session")
    async def test_get_file_contents(
        self, file_in_folder, folder_from_account, base_cli_config_api_with_account_initialized
    ):
        api = base_cli_config_api_with_account_initialized
        file = file_in_folder
        folder = folder_from_account

        response = await api.get_content(file["id"], None, None)

        response_validator = TypeAdapter(GetContentResponse)
        response_validator.validate_python(response, strict=True, from_attributes=True)
        assert response["data"]["parentFolder"] == folder["id"]
        assert response["data"]["type"] == "file"

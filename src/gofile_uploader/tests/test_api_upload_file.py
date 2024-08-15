from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from typing_extensions import List

from src.gofile_uploader.types import CompletedFileUploadResult


class TestAPIFolder:
    @pytest.mark.asyncio(scope="session")
    async def test_upload_file(self, base_cli_config_api_with_account_initialized):
        api = base_cli_config_api_with_account_initialized

        file_path = Path("src/gofile_uploader/tests/example_files/file1.txt")

        response = await api.upload_file(file_path)
        response_validator = TypeAdapter(CompletedFileUploadResult)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_upload_file_to_folder(self, base_cli_config_api_with_account_initialized, folder_from_account):
        api = base_cli_config_api_with_account_initialized

        file_path = Path("src/gofile_uploader/tests/example_files/file1.txt")
        content_id = folder_from_account["id"]

        response = await api.upload_file(file_path, content_id)
        response_validator = TypeAdapter(CompletedFileUploadResult)
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_upload_files(self, base_cli_config_api_with_account_initialized):
        """
        Because no folder id is specified these files will be uploaded to individual and randomly name folders of 6 chars
        """
        api = base_cli_config_api_with_account_initialized

        file_paths = [
            Path("src/gofile_uploader/tests/example_files/file1.txt"),
            Path("src/gofile_uploader/tests/example_files/file2.txt"),
        ]

        response = await api.upload_files(file_paths)
        response_validator = TypeAdapter(List[CompletedFileUploadResult])
        response_validator.validate_python(response, strict=True, from_attributes=True)

    @pytest.mark.asyncio(scope="session")
    async def test_upload_files_to_folder(self, base_cli_config_api_with_account_initialized):
        api = base_cli_config_api_with_account_initialized

        file_paths = [
            Path("src/gofile_uploader/tests/example_files/file1.txt"),
            Path("src/gofile_uploader/tests/example_files/file2.txt"),
        ]

        folder_name = str(uuid4())
        create_folder_response = await api.create_folder(api.root_folder_id, folder_name)
        content_id = create_folder_response["data"]["id"]

        response = await api.upload_files(file_paths, content_id)
        response_validator = TypeAdapter(List[CompletedFileUploadResult])
        response_validator.validate_python(response, strict=True, from_attributes=True)

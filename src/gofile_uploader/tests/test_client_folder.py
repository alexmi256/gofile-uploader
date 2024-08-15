import time

import pytest


class TestClientFolder:
    @pytest.mark.asyncio(scope="session")
    async def test_get_folder_id_no_folder(self, client_with_folder_and_file):
        # id as name and exists
        # id as name but need creation
        client = client_with_folder_and_file["client"]
        folder = client_with_folder_and_file["folder"]
        file = client_with_folder_and_file["file"]

        folder_id = await client.get_folder_id(None)
        assert folder_id == client.api.root_folder_id

    @pytest.mark.asyncio(scope="session")
    async def test_get_folder_id_uuid_folder(self, client_with_folder_and_file):
        # id as name and exists
        # id as name but need creation
        client = client_with_folder_and_file["client"]
        folder = client_with_folder_and_file["folder"]
        file = client_with_folder_and_file["file"]

        folder_id = await client.get_folder_id(folder["data"]["id"])
        assert folder_id == folder["data"]["id"]

    @pytest.mark.asyncio(scope="session")
    async def test_get_folder_id_already_exists(self, client_with_folder_and_file):
        # id as name and exists
        # id as name but need creation
        client = client_with_folder_and_file["client"]
        folder = client_with_folder_and_file["folder"]
        file = client_with_folder_and_file["file"]

        folder_id = await client.get_folder_id(folder["data"]["name"], cache=False)
        assert folder_id == folder["data"]["id"]

    @pytest.mark.asyncio(scope="session")
    async def test_get_folder_id_does_not_exist(self, client_with_folder_and_file):
        # id as name and exists
        # id as name but need creation
        client = client_with_folder_and_file["client"]
        folder = client_with_folder_and_file["folder"]
        file = client_with_folder_and_file["file"]

        folder_id = await client.get_folder_id("a_new_folder", cache=False)
        assert folder_id != folder["data"]["id"]

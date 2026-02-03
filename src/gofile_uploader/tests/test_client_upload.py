from pathlib import Path
from uuid import uuid4

import pytest


class TestClientUpload:
    @pytest.mark.asyncio(scope="session")
    async def test_existing_file_gets_renamed(
        self, renamed_file_in_folder, folder_for_initialized_client, initialized_client
    ):
        # id as name and exists
        # id as name but need creation
        client = initialized_client
        folder = folder_for_initialized_client
        file = renamed_file_in_folder

        folder_id = folder["data"]["id"]
        assert client.options["rename_existing"]

        folder_contents = await client.api.get_content(folder_id, None, None)
        file_before_rename = [
            x for x in folder_contents["data"]["children"].values() if x["md5"] == "35b783efece70cf246f5fa61ba9a4951"
        ]
        assert file_before_rename
        await client.upload_files(client.options["file"], folder_id)

        folder_contents_after = await client.api.get_content(folder_id, cache=False, password=None)
        file_after_rename = [
            x
            for x in folder_contents_after["data"]["children"].values()
            if x["md5"] == "35b783efece70cf246f5fa61ba9a4951"
        ]
        assert file_after_rename
        assert file_after_rename[0]["name"] != file_before_rename[0]["name"]

    @pytest.mark.asyncio(scope="session")
    async def test_upload_global_zone(self, initialized_client):
        client = initialized_client
        original_api_options = client.api.options.get("zone")
        assert original_api_options is None
        test_unique_id = str(uuid4())
        file_path = Path(f"test_upload_global_zone.txt")
        try:
            with open(file_path, "w") as file_to_upload:
                file_to_upload.write(test_unique_id)
            response = await client.api.upload_file(file_path)
            assert response["uploadSuccess"] == "ok"
            pass

        finally:
            try:
                file_path.unlink()
            except FileNotFoundError:
                pass

    @pytest.mark.asyncio(scope="session")
    @pytest.mark.parametrize("zone", ["na", "eu", "sa", "ap"])
    async def test_upload_specific_zone(self, initialized_client, zone):
        # TODO: These tests should be using their own ephemeral clients
        client = initialized_client
        original_api_options = client.api.options.get("zone")
        assert original_api_options is None
        client.api.options["zone"] = zone

        test_unique_id = str(uuid4())
        file_path = Path(f"test_upload_global_zone.txt")
        try:
            with open(file_path, "w") as file_to_upload:
                file_to_upload.write(test_unique_id)
            response = await client.api.upload_file(file_path)
            assert response["uploadSuccess"] == "ok"

        finally:
            try:
                client.api.options["zone"] = None
                assert client.api.options["zone"] is None
                file_path.unlink()
            except FileNotFoundError:
                pass

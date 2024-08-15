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

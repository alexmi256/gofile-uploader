import asyncio
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

from src.gofile_uploader.api import GofileIOAPI
from src.gofile_uploader.gofile_uploader import GofileIOUploader, cli

BASE_CONFIG = {
    "token": None,
    "zone": None,
    "connections": 1,
    "public": False,
    "save": False,
    "retries": 1,
    "history": {
        "md5_sums": {},
        "uploads": [],
    },
    "dry_run": False,
    "debug_save_js_locally": False,
    "rename_existing": True,
    "use_config": False,
    "timeout": 600,
    "log_level": "warning",
    "log_file": None,
    "folder": None,
    "file": Path("src/gofile_uploader/tests/example_files/file1.txt"),
    "hash_pool_size": 1,
    "config_file_path": None,
    "config_directory": None,
}


@pytest.fixture(scope="session")
def event_loop(request):
    loop = asyncio.get_event_loop_policy().get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def base_cli_config():
    return deepcopy(BASE_CONFIG)


@pytest_asyncio.fixture(scope="session")
async def base_cli_config_api(base_cli_config):
    api = GofileIOAPI(base_cli_config)
    yield api
    if not api.session.closed:
        await api.session.close()


@pytest_asyncio.fixture(scope="session")
async def base_cli_config_api_debug_save_js_locally(base_cli_config):
    config = deepcopy(base_cli_config)
    config["debug_save_js_locally"] = True

    api = GofileIOAPI(config)
    yield api
    if not api.session.closed:
        await api.session.close()


# FIXME: No idea why but setting a scope on this will fail and complain about scope mismatch if I don't mark the test
#  with the session scope or if I try to reuse the base_cli_config fixture
#  The different scopes for asyncio seems like a known pain point from devs
#  https://stackoverflow.com/questions/63713575/pytest-issues-with-a-session-scoped-fixture-and-asyncio
#  https://github.com/pytest-dev/pytest-asyncio/issues/744
#  https://github.com/pytest-dev/pytest-asyncio/issues/706
@pytest_asyncio.fixture(scope="session")
async def base_cli_config_api_with_account():
    existing_api_key = os.environ.get("GOFILE_TOKEN")
    if existing_api_key:
        token = existing_api_key.strip()
    else:
        new_account = await GofileIOAPI.get_new_account()
        token = new_account["data"]["token"]

    config = deepcopy(BASE_CONFIG)

    config["token"] = token
    api = GofileIOAPI(config)

    yield api
    if not api.session.closed:
        await api.session.close()


@pytest_asyncio.fixture(scope="session")
async def base_cli_config_api_with_account_initialized():
    existing_api_key = os.environ.get("GOFILE_TOKEN")
    if existing_api_key:
        token = existing_api_key.strip()
    else:
        new_account = await GofileIOAPI.get_new_account()
        token = new_account["data"]["token"]

    config = deepcopy(BASE_CONFIG)

    config["token"] = token
    api = GofileIOAPI(config)
    await api.init()

    yield api

    root_folder_contents = await api.get_content(api.root_folder_id, False, None)
    root_folder_items: list[str] = root_folder_contents["data"]["children"].keys()  # type: ignore
    if root_folder_items:
        await api.delete_contents(root_folder_items)

    if not api.session.closed:
        await api.session.close()

    for server_session in api.server_sessions.values():
        if not server_session.closed:
            await server_session.close()


@pytest_asyncio.fixture(scope="session")
async def folder_from_account(base_cli_config_api_with_account_initialized):
    api = base_cli_config_api_with_account_initialized
    folder_name = str(uuid4())
    create_folder_response = await api.create_folder(api.root_folder_id, folder_name)
    yield create_folder_response["data"]
    # No need to cleanup, base_cli_config_api_with_account_initialized does this for us


@pytest_asyncio.fixture(scope="session")
async def file_in_folder(base_cli_config_api_with_account_initialized, folder_from_account):
    api = base_cli_config_api_with_account_initialized

    file_path = Path("src/gofile_uploader/tests/example_files/file1.txt")
    content_id = folder_from_account["id"]

    file_uploaded = await api.upload_file(file_path, content_id)
    yield file_uploaded


@pytest_asyncio.fixture(scope="session")
async def initialized_client(base_cli_config):
    config = deepcopy(base_cli_config)

    existing_api_key = os.environ.get("GOFILE_TOKEN")
    if existing_api_key:
        token = existing_api_key.strip()
    else:
        new_account = await GofileIOAPI.get_new_account()
        token = new_account["data"]["token"]

    config["token"] = token

    client = GofileIOUploader(config)
    await client.api.init()

    yield client

    await client.cleanup_api_sessions()


@pytest_asyncio.fixture(scope="session")
async def folder_for_initialized_client(initialized_client):
    client = initialized_client

    folder_name = str("test_folder_2")
    create_folder_response = await client.api.create_folder(client.api.root_folder_id, folder_name)

    yield create_folder_response

    root_folder_contents = await client.api.get_content(client.api.root_folder_id, None, None)
    root_folder_items: list[str] = root_folder_contents["data"]["children"].keys()  # type: ignore
    if root_folder_items:
        await client.api.delete_contents(root_folder_items)


@pytest_asyncio.fixture(scope="session")
async def renamed_file_in_folder(folder_for_initialized_client, initialized_client):
    client = initialized_client
    folder = folder_for_initialized_client

    file_path = Path("src/gofile_uploader/tests/example_files/file1-copy.txt")

    with open(file_path, "x") as file:
        file.write("hello world 1")

    content_id = folder["data"]["id"]

    file_uploaded = await client.api.upload_file(file_path, content_id)

    yield file_uploaded

    file_path.unlink(missing_ok=True)


@pytest_asyncio.fixture(scope="session")
async def client_with_folder_and_file(base_cli_config):
    config = deepcopy(base_cli_config)

    existing_api_key = os.environ.get("GOFILE_TOKEN")
    if existing_api_key:
        token = existing_api_key.strip()
    else:
        new_account = await GofileIOAPI.get_new_account()
        token = new_account["data"]["token"]

    config["token"] = token

    client = GofileIOUploader(config)
    await client.api.init()

    folder_name = str("test_folder")
    create_folder_response = await client.api.create_folder(client.api.root_folder_id, folder_name)
    file_path = Path("src/gofile_uploader/tests/example_files/file1.txt")

    file_uploaded = await client.api.upload_file(file_path, create_folder_response["data"]["id"])

    data = {"client": client, "folder": create_folder_response, "file": file_uploaded}

    yield data

    root_folder_contents = await client.api.get_content(client.api.root_folder_id, None, None)
    root_folder_items: list[str] = root_folder_contents["data"]["children"].keys()  # type: ignore
    if root_folder_items:
        await client.api.delete_contents(root_folder_items)
    await client.cleanup_api_sessions()

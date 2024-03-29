import argparse
import asyncio
import csv
import logging
import os
import time
from io import BufferedReader
from pathlib import Path
from pprint import pformat, pprint
from typing import Callable, Literal, Optional

import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

from src.gofile_uploader.types import (
    CreateFolderData,
    GetAccountDetailsResponse,
    GetAccountIdResponse,
    GetContentResponse,
    GetServersResponse,
    UpdateContentOption,
    UpdateContentOptionValue,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


class ProgressFileReader(BufferedReader):
    def __init__(self, filename: Path, read_callback: Optional[Callable[[int, int, Optional[int]], None]] = None):
        # Don't use with because we need the file to be open for future progress
        # No idea if this causes memory issues
        f = open(filename, "rb")
        self.__read_callback = read_callback
        super().__init__(raw=f)
        self.length = Path(filename).stat().st_size

    def read(self, size: Optional[int] = None):
        calc_sz = size
        if not calc_sz:
            calc_sz = self.length - self.tell()
        if self.__read_callback:
            self.__read_callback(self.tell(), round(self.tell() / self.length), self.length)
        return super(ProgressFileReader, self).read(size)


class TqdmUpTo(tqdm):
    """Provides `update_to(n)` which uses `tqdm.update(delta_n)`."""

    def update_to(self, b=1, bsize=1, tsize=None):
        """
        b  : int, optional
            Number of blocks transferred so far [default: 1].
        bsize  : int, optional
            Size of each block (in tqdm units) [default: 1].
        tsize  : int, optional
            Total size (in tqdm units). If [default: None] remains unchanged.
        """
        if tsize is not None:
            self.total = tsize
        return self.update(b * bsize - self.n)  # also sets self.n = b * bsize


class GofileIOAPI:
    def __init__(
        self, token: Optional[str] = None, max_connections: int = 4, zone: Optional[Literal["eu", "na"]] = None
    ):
        self.token = token
        self.session_headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        self.session = aiohttp.ClientSession("https://api.gofile.io", headers=self.session_headers)
        self.zone = zone
        self.root_folder_id = None
        self.account_id = None
        self.is_premium = False
        self.make_public = False
        self.server_sessions = {}
        self.created_folders = {}
        self.sem = asyncio.Semaphore(max_connections)

    async def init(self):
        account_id = await self.get_account_id()
        self.account_id = account_id["data"]["id"]

        if self.token is not None:
            account = await self.get_account_details(self.account_id)
            self.root_folder_id = account["data"]["rootFolder"]
            self.is_premium = account["data"]["tier"] != "standard"

    def check_public_account(self):
        if self.token is None:
            raise Exception(f"Cannot perform functionality for public account, create and account and provide a token")

    def check_premium_status(self):
        self.check_public_account()
        if self.is_premium is False:
            raise Exception(f"Account tier is standard but needs to be premium")

    async def get_servers(self, zone: Optional[Literal["eu", "na"]]) -> GetServersResponse:
        params = {"zone": zone} if zone else None
        async with self.session.get("/servers", params=params) as resp:
            response = await resp.json()
            if "status" not in response or response["status"] != "ok":
                logger.error(pformat(response))
                raise Exception(response)
            return response

    async def get_account_id(self) -> GetAccountIdResponse:
        self.check_public_account()
        async with self.session.get("/accounts/getid") as resp:
            response = await resp.json()
            logger.debug(f'Account id is "{response["data"]["id"]}"')
            return response

    async def get_account_details(self, account_id: str) -> GetAccountDetailsResponse:
        self.check_public_account()
        async with self.session.get(f"/accounts/{account_id}") as resp:
            response = await resp.json()
            logger.debug(f'Account details for "{account_id}" are {response["data"]}')
            return response

    async def set_premium_status(self) -> None:
        account = await self.get_account_details(self.account_id)
        self.is_premium = account["data"]["tier"] != "standard"

    async def get_content(self, content_id: str, cache: Optional[bool], password: Optional[str]) -> GetContentResponse:
        # Requires Premium
        self.check_premium_status()

        params = {}
        if cache:
            params["cache"] = cache
        if password:
            params["password"] = password

        async with self.session.get(f"/contents/{content_id}", params=params) as resp:
            response = await resp.json()
            return response

    async def create_folder(self, parent_folder_id: str, folder_name: Optional[str]) -> CreateFolderData:
        self.check_public_account()
        data = {"parentFolderId": parent_folder_id}
        if folder_name:
            data["folderName"] = folder_name

        logger.debug(f"Creating new folder '{folder_name}' in parent folder id '{parent_folder_id}' ")
        async with self.session.post("/contents/createfolder", data=data) as resp:
            response = await resp.json()
            if "status" not in response or response["status"] != "ok":
                raise Exception(response)
            logger.debug(
                f'Folder "{response["data"]["name"]}" ({response["data"]["folderId"]}) created in {response["data"]["parentFolder"]}'
            )
            self.created_folders[folder_name] = response["data"]
            return response["data"]

    async def update_content(
        self, content_id: str, option: UpdateContentOption, value: UpdateContentOptionValue
    ) -> CreateFolderData:
        data = {"attribute": option, "attributeValue": value}
        async with self.session.put(f"/contents/{content_id}/update", data=data) as resp:
            response = await resp.json()
            if "status" not in response or response["status"] != "ok":
                raise Exception(response)
            return response["data"]

    async def upload_file(self, file_path: Path, folder_id: Optional[str] = None, tqdm_index=1) -> list[str]:
        async with self.sem:
            retries = 0
            while retries < 3:
                try:
                    # TODO: Rate limit to one request every 10 seconds
                    servers = await self.get_servers(zone=self.zone)

                    server = next(iter(servers["data"]["servers"]))["name"]
                    if server not in self.server_sessions:
                        logger.info(f"Using new server connection to {server}")
                        self.server_sessions[server] = aiohttp.ClientSession(
                            f"https://{server}.gofile.io", headers=self.session_headers
                        )

                    session = self.server_sessions[server]

                    # I couldn't get CallbackIOWrapper to work due to "Can not serialize value type: <class 'tqdm.utils.CallbackIOWrapper'>"
                    # Maybe someone can try and get better results
                    with TqdmUpTo(unit="B", unit_scale=True, unit_divisor=1024, miniters=1, desc=file_path.name) as t:
                        with ProgressFileReader(filename=file_path, read_callback=t.update_to) as upload_file:
                            data = aiohttp.FormData()
                            data.add_field("file", upload_file, filename=file_path.name)
                            logger.debug(f'File "{file_path.name}" was selected for upload')
                            if folder_id:
                                logger.debug(f'File {file_path.name} will be uploaded to folder id "{folder_id}"')
                                data.add_field("folderId", folder_id)
                            else:
                                logger.debug(
                                    f"File {file_path.name} will be uploaded to a new randomly created folder id"
                                )

                            async with session.post("/contents/uploadfile", data=data) as resp:
                                response = await resp.json()
                                if "status" not in response or response["status"] != "ok":
                                    raise Exception(
                                        f'File {file_path.name} failed upload load due to missing or not "ok" status in response:\n{pformat(response)}'
                                    )
                                return [response["data"]["fileName"], response["data"]["downloadPage"]]

                except Exception as e:
                    retries += 1
                    logger.error(f"Failed to upload {file_path} due to:\n", exc_info=e)

    async def upload_files(self, paths: list[Path], folder_id: Optional[str] = None) -> list[list[str]]:
        try:
            tasks = [self.upload_file(test_file, folder_id, i + 1) for i, test_file in enumerate(paths)]
            responses = await tqdm_asyncio.gather(*tasks, desc="Files uploaded")
            # FIXME: Need to fix responses
            return responses
        finally:
            # This should happen in the API client itself
            await self.session.close()
            for server_session in self.server_sessions.values():
                await server_session.close()


class GofileIOUploader:
    def __init__(
        self,
        token: Optional[str] = None,
        max_connections: int = 4,
        make_public: bool = False,
        zone: Optional[Literal["eu", "na"]] = None,
    ):
        self.api = GofileIOAPI(token, max_connections=max_connections, zone=zone)
        self.make_public = make_public

    async def init(self) -> None:
        try:
            if self.api.token is not None:
                await self.api.init()

        except Exception as ex:
            logger.error(ex)
            await self.api.session.close()

    async def get_folder_id(self, folder: Optional[str]) -> Optional[str]:
        folder_id = None

        if folder is None:
            return None
        elif self.api.token:
            if folder:
                # Check if the folder is already the root folder id for the account
                if folder == self.api.root_folder_id:
                    folder_id = folder
                else:
                    # Create the folder
                    # TODO: With premium it would be nice to query folder to see if it already exists on gofile
                    new_folder = await self.api.create_folder(self.api.root_folder_id, folder)
                    folder_id = new_folder["folderId"]
            else:
                # Set account root folder by default
                folder_id = self.api.root_folder_id

        return folder_id

    async def upload_files(self, path: str, folder: Optional[str] = None, save: bool = True):
        contents = Path(path)

        if contents.is_file():
            paths = [contents]
        else:
            paths = [x for x in contents.iterdir()]
            if folder is None:
                folder = contents.name
        folder_id = await self.get_folder_id(folder)

        if self.make_public and folder_id != self.api.root_folder_id:
            logger.info(f"Making folder {folder_id} public")
            await self.api.update_content(folder_id, "public", "true")

        responses = await self.api.upload_files(paths, folder_id)
        if save:
            file_name = f"gofile_upload_{int(time.time())}.csv"
            with open(file_name, "w", newline="") as csvfile:
                logger.info(f"Saving uploaded files to {file_name}")
                csv_writer = csv.writer(csvfile, dialect="excel")
                csv_writer.writerows(responses)
        else:
            pprint(responses)


async def main() -> None:
    parser = argparse.ArgumentParser(
        prog="GofileIOUploader", description="Gofile.io Uploader supporting parallel uploads"
    )
    parser.add_argument("file", type=str, help="File or directory to look for files in to upload")
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        help="""API token for your account so that you can upload to a specific account/folder.
        You can also set the GOFILE_TOKEN environment variable for this""",
    )
    parser.add_argument(
        "-z",
        "--zone",
        type=str,
        choices=["na", "eu"],
        help="Server zone to prefer uploading to",
    )
    parser.add_argument(
        "-f", "--folder", type=str, help="Folder to upload files to overriding the directory name if used"
    )
    parser.add_argument("-c", "--connections", type=int, default=6, help="Maximum parallel uploads to do at once")
    parser.add_argument(
        "--public",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Make all files uploaded public. By default they are private and not unsharable",
    )
    parser.add_argument(
        "--save",
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Don\'t save uploaded file urls to a "gofile_upload_<unixtime>.json" file',
    )
    args = parser.parse_args()

    token = args.token or os.getenv("GOFILE_TOKEN")

    client = GofileIOUploader(token, max_connections=args.connections, make_public=args.public, zone=args.zone)
    try:
        await client.init()
        await client.upload_files(args.file, args.folder, args.save)
    finally:
        if not client.api.session.closed:
            await client.api.session.close()


asyncio.run(main())

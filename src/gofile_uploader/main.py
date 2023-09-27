import argparse
import asyncio
import json
import logging
import os
import time
from io import BufferedReader
from pathlib import Path
from pprint import pformat, pprint
from typing import Callable, Literal, TypedDict, Union

import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


class ServerResponse(TypedDict):
    status: str


class CreateFolderData(TypedDict):
    id: str
    type: str
    name: str
    parentFolder: str
    createTime: int
    childs: list[str]
    code: str


class CreateFolderResponse(ServerResponse):
    data: CreateFolderData


class GetAccountDetailsData(TypedDict):
    token: str
    email: str
    tier: str
    rootFolder: str
    filesCount: int
    total30DDLTraffic: int
    credit: int
    currency: str
    currencySign: str


class GetAccountDetailsResponse(ServerResponse):
    data: GetAccountDetailsData


class GetContentIndividualContent(TypedDict):
    id: str
    type: str
    name: str
    parentFolder: str
    createTime: int
    size: int
    downloadCount: int
    md5: str
    mimetype: str
    serverChoosen: str
    directLink: str
    link: str


class GetContentData(TypedDict):
    isOwner: bool
    id: str
    type: str
    name: str
    parentFolder: str
    code: str
    createTime: int
    public: bool
    childs: list[str]
    totalDownloadCount: int
    totalSize: int
    contents: dict[str, GetContentIndividualContent]


class GetContentResponse(ServerResponse):
    data: GetContentData


SetOptionOption = Literal["public", "password", "description", "expire", "tags", "directLink"]


"""
For "public", can be "true" or "false". The contentId must be a folder.
For "password", must be the password. The contentId must be a folder.
For "description", must be the description. The contentId must be a folder.
For "expire", must be the expiration date in the form of unix timestamp. The contentId must be a folder.
For "tags", must be a comma seperated list of tags. The contentId must be a folder.
For "directLink", can be "true" or "false". The contentId must be a file.
"""
SetOptionValue = Union[str, int, list[str]]


class UploadFileData(TypedDict):
    guestToken: str
    downloadPage: str
    code: str
    parentFolder: str
    fileId: str
    fileName: str
    md5: str


class UploadFileResponse(ServerResponse):
    data: UploadFileData


class GofileCLIArgs(TypedDict):
    file: str
    token: Union[str, None]
    folder: Union[str, None]
    connections: int
    public: bool
    no_save: bool


class ProgressFileReader(BufferedReader):
    def __init__(self, filename: Path, read_callback: Union[Callable[[int, int, Union[int, None]], None], None] = None):
        # Don't use with because we need the file to be open for future progress
        # No idea if this causes memory issues
        f = open(filename, "rb")
        self.__read_callback = read_callback
        super().__init__(raw=f)
        self.length = Path(filename).stat().st_size

    def read(self, size: Union[int, None] = None):
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
    def __init__(self, token: Union[str, None] = None, max_connections: int = 4):
        self.token = token
        self.session = aiohttp.ClientSession("https://api.gofile.io")
        self.root_folder_id = None
        self.is_premium = False
        self.make_public = False
        self.server_sessions = {}
        self.created_folders = {}
        self.sem = asyncio.Semaphore(max_connections)

    async def init(self):
        if self.token is not None:
            account = await self.get_account_details()
            self.root_folder_id = account["data"]["rootFolder"]
            self.is_premium = account["data"]["tier"] != "standard"

    def check_public_account(self):
        if self.token is None:
            raise Exception(f"Cannot perform functionality for public account, create and account and provide a token")

    def check_premium_status(self):
        self.check_public_account()
        if self.is_premium is False:
            raise Exception(f"Account tier is standard but needs to be premium")

    async def get_server(self) -> str:
        async with self.session.get("/getServer") as resp:
            response = await resp.json()
            if "status" not in response or response["status"] != "ok":
                logger.error(pformat(response))
                raise Exception(response)
            return response["data"]["server"]

    async def get_account_details(self) -> GetAccountDetailsResponse:
        self.check_public_account()
        params = {
            "token": self.token,
        }
        async with self.session.get("/getAccountDetails", params=params) as resp:
            response = await resp.json()
            return response

    async def set_premium_status(self) -> None:
        account = await self.get_account_details()
        self.is_premium = account["data"]["tier"] != "standard"

    async def get_content(self, content_id: str) -> GetContentResponse:
        self.check_premium_status()

        params = {
            "token": self.token,
            "contentId": content_id,
        }
        async with self.session.get("/getContent", params=params) as resp:
            response = await resp.json()
            return response

    async def create_folder(self, parent_folder_id: str, folder_name: str) -> CreateFolderData:
        self.check_public_account()
        data = {"token": self.token, "parentFolderId": parent_folder_id, "folderName": folder_name}
        logger.debug(f"Creating new folder {folder_name}")
        async with self.session.put("/createFolder", data=data) as resp:
            response = await resp.json()
            if "status" not in response or response["status"] != "ok":
                raise Exception(response)
            self.created_folders[folder_name] = response["data"]
            return response["data"]

    async def set_option(self, content_id: str, option: SetOptionOption, value: SetOptionValue) -> CreateFolderData:
        data = {"contentId": content_id, "token": self.token, "option": option, "value": value}
        async with self.session.put("/setOption", data=data) as resp:
            response = await resp.json()
            if "status" not in response or response["status"] != "ok":
                raise Exception(response)
            return response["data"]

    async def upload_file(self, file_path: Path, folder_id: Union[str, None] = None, tqdm_index=1) -> str:
        async with self.sem:
            retries = 0
            while retries < 3:
                try:
                    server = await self.get_server()
                    if server not in self.server_sessions:
                        logger.info(f"Using new server connection to {server}")
                        self.server_sessions[server] = aiohttp.ClientSession(f"https://{server}.gofile.io")

                    session = self.server_sessions[server]

                    # I couldn't get CallbackIOWrapper to work due to "Can not serialize value type: <class 'tqdm.utils.CallbackIOWrapper'>"
                    # Maybe someone can try and get better results
                    with TqdmUpTo(unit="B", unit_scale=True, unit_divisor=1024, miniters=1, desc=file_path.name) as t:
                        with ProgressFileReader(filename=file_path, read_callback=t.update_to) as upload_file:
                            data = aiohttp.FormData()
                            data.add_field("file", upload_file, filename=file_path.name)
                            if self.token:
                                data.add_field("token", self.token)
                                if folder_id:
                                    data.add_field("folderId", folder_id)

                            async with session.post("/uploadFile", data=data) as resp:
                                response = await resp.json()
                                if "status" not in response or response["status"] != "ok":
                                    raise Exception(
                                        f'File {file_path.name} failed upload load due to missing or not "ok" status in response:\n{pformat(response)}'
                                    )
                                return f"{response['data']['fileName']} uploaded to {response['data']['downloadPage']}"

                except Exception as e:
                    retries += 1
                    logger.error(f"Failed to upload {file_path} due to:\n", exc_info=e)

    async def upload_files(self, paths: list[Path], folder_id: Union[str, None] = None) -> list[dict]:
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
    def __init__(self, token: Union[str, None] = None, max_connections: int = 4, make_public: bool = False):
        self.api = GofileIOAPI(token, max_connections)
        self.make_public = make_public

    async def init(self) -> None:
        try:
            if self.api.token is not None:
                await self.api.init()

        except Exception as ex:
            logger.error(ex)
            await self.api.session.close()

    async def get_folder_id(self, folder: Union[str, None]) -> Union[str, None]:
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
                    folder_id = new_folder["id"]
            else:
                # Set account root folder by default
                folder_id = self.api.root_folder_id

        return folder_id

    async def upload_files(self, path: str, folder: Union[str, None] = None, save: bool = True):
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
            await self.api.set_option(folder_id, "public", "true")

        responses = await self.api.upload_files(paths, folder_id)
        if save:
            file_name = f"gofile_upload_{int(time.time())}.json"
            with open(file_name, "w+") as saved_file:
                logger.info(f"Save uploaded files to {file_name}")
                json.dump(responses, saved_file, indent=4)
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
        help="API token for your account so that you can upload to a specific account/folder. You can also set the GOFILE_TOKEN environment variable for this",
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

    client = GofileIOUploader(token, args.connections, args.public)
    try:
        await client.init()
        await client.upload_files(args.file, args.folder, args.save)
    finally:
        if not client.api.session.closed:
            await client.api.session.close()


asyncio.run(main())

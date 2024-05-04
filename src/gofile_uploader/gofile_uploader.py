import argparse
import asyncio
import csv
import logging
import os
import hashlib
import re
import time
import json
from io import BufferedReader
from pathlib import Path
from pprint import pformat, pprint
from typing import Callable, Literal, Optional, Any

import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

from .types import (
    CreateFolderData,
    GetAccountDetailsResponse,
    GetAccountIdResponse,
    GetContentResponse,
    GetServersResponse,
    UpdateContentOption,
    UpdateContentOptionValue,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


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
        self,
        token: Optional[str] = None,
        max_connections: int = 4,
        zone: Optional[Literal["eu", "na"]] = None,
        retries: int = 1,
        options: Optional[dict[str, Any]] = None,
    ):
        if options is None:
            options = {}
        self.options = options
        self.token = token
        self.session_headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        self.wt = None
        self.session = aiohttp.ClientSession("https://api.gofile.io", headers=self.session_headers)
        self.zone = zone
        self.root_folder_id = None
        self.account_id = None
        self.is_premium = False
        self.make_public = False
        self.server_sessions = {}
        self.created_folders = {}
        self.sem = asyncio.Semaphore(max_connections)
        self.retries = retries

    async def init(self):
        account_id = await self.get_account_id()
        self.account_id = account_id["data"]["id"]

        if self.wt is None:
            self.wt = await self.get_wt()

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

    async def get_wt(self) -> Optional[str]:
        # Maybe one day I'll figure out what this stands for
        wt = None
        async with aiohttp.ClientSession() as session:
            async with session.get("https://gofile.io/dist/js/alljs.js") as resp:
                response = await resp.text()
                if self.options.get('debug_save_js_locally'):
                    response_hash = hashlib.md5(response.encode("utf-8")).hexdigest()
                    file_name = Path(f"gofile-alljs-{response_hash}.js")
                    if file_name.exists():
                        logger.debug(f"Gofile script {file_name} was retrieved but already existed locally")
                    else:
                        with open(file_name, "w") as file:
                            file.write(response)
                            logger.debug(f"Gofile script {file_name} was retrieved and saved locally")
                wt_search = re.search(r"wt:\s*\"(\w{12})\"", response)
                if wt_search:
                    wt = wt_search.groups()[0]
                    logger.debug(f"Gofile wt was successfully extracted as {wt}")
                else:
                    logger.error(f"Failed to fetch gofile wt")
        return wt

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
            while retries < self.retries:
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
        retries: int = 1,
        options: Optional[dict[str, Any]] = None,
    ):
        # I hate having these in both Uploader and Client but client is supposed to be dumb and have less logic
        # which leads to annoying complexity
        if options is None:
            options = {}
        self.options = options

        self.api = GofileIOAPI(
            token, max_connections=max_connections, zone=zone, retries=retries, options=options
        )
        self.make_public = make_public

        # Let's create and/or load a config if one was used
        home_path = Path.home()

        self.config_directory = home_path.joinpath(".config", "gofile-upload")
        self.config_file_path = self.config_directory.joinpath('config.json')
        # Only use a config if the user has authorized (which is set to true by default)
        self.load_config_file()

    async def init(self) -> None:
        try:
            if self.api.token is not None:
                await self.api.init()
            # We should get the wt even if we don't have an account
            if self.api.wt is None:
                self.api.wt = await self.api.get_wt()

        except Exception as ex:
            logger.error(ex)
            await self.api.session.close()

    def save_config_file(self):
        """
        Creates the config directory and file with the current config options if using config is enabled
        """
        if self.options.get("use_config"):
            if not self.config_directory.exists():
                logger.info(f'Creating config directory at {self.config_directory}')
                self.config_directory.mkdir(parents=True, exist_ok=True)

            with open(self.config_file_path, 'w') as config_file:
                logger.debug(f'Saving config to {self.config_file_path}')
                json.dump(self.options['config'], config_file,  indent=2)
        else:
            logger.error(f'Config file is not in use')

    def load_config_file(self):
        """
        Loads the config file to config options if using config is enabled
        """
        if self.options.get("use_config"):
            if self.config_file_path.exists():
                with open(self.config_file_path, 'r') as config_file:
                    logger.debug(f'Loading config from {self.config_file_path}')
                    try:
                        self.options['config'] = json.load(config_file)
                    except Exception:
                        logger.exception(f'Failed to load config file {self.config_file_path} as a JSON config')
            else:
                logger.error(f'Could not load config file {self.config_file_path} because it did not exist')
                self.options['config'] = {}
                self.save_config_file()
        else:
            logger.error(f'Config file is not in use')

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
        if save and responses:
            file_name = f"gofile_upload_{int(time.time())}.csv"
            with open(file_name, "w", newline="") as csvfile:
                logger.info(f"Saving uploaded files to {file_name}")
                csv_writer = csv.writer(csvfile, dialect="excel")
                csv_writer.writerows([x for x in responses if x])
        else:
            pprint(responses)


def cli():
    parser = argparse.ArgumentParser(prog="gofile-upload", description="Gofile.io Uploader supporting parallel uploads")
    parser.add_argument("file", type=str, help="File or directory to look for files in to upload")
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        default=os.getenv("GOFILE_TOKEN"),
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
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Don't create folders or upload files",
    )
    parser.add_argument(
        "--debug-save-js-locally",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Debug option to save the retrieved js file locally",
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
        help='Don\'t save uploaded file urls to a "gofile_upload_<unixtime>.csv" file',
    )
    parser.add_argument(
        "--use-config",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to create and use a config file in $HOME/.config/gofile_upload/config.json",
    )
    parser.add_argument(
        "-r",
        "--retries",
        default=3,
        type=int,
        help="How many times to retry a failed upload",
    )
    args = parser.parse_args()

    return args


async def async_main() -> None:
    args = cli()
    logger.debug(args)

    options = {}
    if args.debug_save_js_locally:
        options["debug_save_js_locally"] = args.debug_save_js_locally
    if args.use_config:
        options["use_config"] = args.use_config

    gofile_client = GofileIOUploader(
        args.token,
        max_connections=args.connections,
        make_public=args.public,
        zone=args.zone,
        retries=args.retries,
        options=options,
    )

    try:
        await gofile_client.init()
        if args.dry_run:
            print("Dry run only, uploading skipped")
        else:
            await gofile_client.upload_files(args.file, args.folder, args.save)
    finally:
        if not gofile_client.api.session.closed:
            await gofile_client.api.session.close()


def main():
    asyncio.run(async_main())

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import re
import time
from io import BufferedReader
from pathlib import Path
from pprint import pformat, pprint
from typing import Any, Callable, Literal, Optional

import aiohttp
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

from .types import (
    CompletedFileUploadResult,
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
                if self.options.get("debug_save_js_locally"):
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
        if not self.wt:
            self.check_premium_status()

        params = {}
        if cache:
            params["cache"] = "true"
        if self.wt:
            params["wt"] = self.wt
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

    async def upload_file(self, file_path: Path, folder_id: Optional[str] = None) -> CompletedFileUploadResult:
        file_metadata = {
            "filePath": str(file_path),
            "filePathMD5": hashlib.md5(str(file_path).encode("utf-8")).hexdigest(),
            "fileNameMD5": hashlib.md5(str(file_path.name).encode("utf-8")).hexdigest(),
            "uploadSuccess": None,
        }
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
                                file_metadata.update(response["data"])
                                file_metadata["uploadSuccess"] = response.get("status")
                                if file_metadata["uploadSuccess"] == "ok":
                                    self.options["config"]["history"]["uploads"].append(file_metadata)
                                return file_metadata

                except Exception as e:
                    retries += 1
                    logger.error(f"Failed to upload {file_path} due to:\n", exc_info=e)

                return file_metadata

    async def upload_files(self, paths: list[Path], folder_id: Optional[str] = None) -> list[CompletedFileUploadResult]:
        try:
            tasks = [self.upload_file(test_file, folder_id) for i, test_file in enumerate(paths)]
            responses = await tqdm_asyncio.gather(*tasks, desc="Files uploaded")
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

        self.api = GofileIOAPI(token, max_connections=max_connections, zone=zone, retries=retries, options=options)
        self.make_public = make_public

        # Let's create and/or load a config if one was used
        home_path = Path.home()

        self.config_directory = home_path.joinpath(".config", "gofile-upload")
        self.config_file_path = self.config_directory.joinpath("config.json")
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
                logger.info(f"Creating config directory at {self.config_directory}")
                self.config_directory.mkdir(parents=True, exist_ok=True)

            with open(self.config_file_path, "w") as config_file:
                logger.debug(f"Saving config to {self.config_file_path}")
                json.dump(self.options["config"], config_file, indent=2)
        else:
            logger.error(f"Config file is not in use")

    def load_config_file(self):
        """
        Loads the config file to config options if using config is enabled
        """
        if self.options.get("use_config"):
            if self.config_file_path.exists():
                with open(self.config_file_path, "r") as config_file:
                    logger.debug(f"Loading config from {self.config_file_path}")
                    try:
                        self.options["config"] = json.load(config_file)
                    except Exception:
                        logger.exception(f"Failed to load config file {self.config_file_path} as a JSON config")
            else:
                logger.error(f"Could not load config file {self.config_file_path} because it did not exist")
                self.create_config_defaults()
                self.save_config_file()
        else:
            logger.error(f"Config file is not in use, creating them in memory only")
            self.create_config_defaults()

    def create_config_defaults(self):
        if self.options["use_config"]:
            if "config" not in self.options:
                self.options["config"] = {}
            if "history" not in self.options["config"]:
                self.options["config"]["history"] = {}
            if "uploads" not in self.options["config"]["history"]:
                self.options["config"]["history"]["uploads"] = []
            if "md5_sums" not in self.options["config"]["history"]:
                self.options["config"]["history"]["md5_sums"] = {}
        else:
            logger.error(f"Config file is not in use")

    async def get_folder_id(self, folder: Optional[str]) -> Optional[str]:
        """
        Get the id of a folder's name
        A folder should be the name of the folder you want to retrieve the id of but can also be the root id
        """

        # No folder provided, try to use root folder
        if folder is None:
            logger.warning("No folder was specified")
            if self.api.token:
                # When no folder is specified and the user has an account, upload to the root folder
                logger.debug("Using root folder id since we have an API token")
                return self.api.root_folder_id
            else:
                logger.warning("Poorly supported: No API token exists, need to create an temporary account")
                # TODO If the user has not specified a token for an account we should create an account on the fly so they
                #  can keep all uploads in that folder
                return None
        # Folder is UUIDv4, assume user is referencing to something already created
        elif re.match(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", folder):
            logger.warning(
                "For some reason the given folder name to create was a UUID so we will assume it already exists"
            )
            return folder
        # Folder needs to be created or already exists
        elif self.api.token:
            root_folder_contents = await self.api.get_content(self.api.root_folder_id, cache=True, password=None)

            # Another case that tbh don't name much sense but the user might specify "root" folder name which
            # is usually the root folder name
            if root_folder_contents["data"]["name"] == folder:
                logger.info("The folder we wanted to create ended up being the account root folder")
                return root_folder_contents["data"]["id"]

            # Check in the root folder if there is a directory with that name already
            # We're only trying this one level deep otherwise we'd have to do recursive stuff I don't care to do atm
            folder_with_same_name = next(
                (
                    x
                    for x in root_folder_contents["data"].get("children", {}).values()
                    if x.get("type") == "folder" and x.get("name") == folder
                ),
                None,
            )
            if folder_with_same_name:
                logger.info(
                    f"Found folder \"{folder_with_same_name['name']}\" ({folder_with_same_name['id']}) inside root folder ({self.api.root_folder_id}), will reuse"
                )
                return folder_with_same_name["id"]
            else:
                # We couldn't find a previosuly created folder with the same name so we should create a new one
                logger.info(
                    f'Could not find a folder inside the root folder with the name "{folder}" so we will create one'
                )
                new_folder = await self.api.create_folder(self.api.root_folder_id, folder)
                return new_folder["folderId"]
        else:
            logger.warning("User did not provide an account or a folder name, should create temp account")
            return None

    def get_md5_sums_for_files(self, paths: list[Path]) -> dict[str, str]:
        # Create the config paths for easier lookups just in case they didn't exist
        self.create_config_defaults()

        sums = {}

        # TODO: Try to parallelize this
        for path in paths:
            if path.is_file():
                if str(path) in self.options["config"]["history"]["md5_sums"]:
                    md5_sum_for_file = self.options["config"]["history"]["md5_sums"][str(path)]
                    logger.debug(
                        f'Found precomputed md5sum ({md5_sum_for_file}) for path "{path}" using md5_sums config history'
                    )
                    sums[str(path)] = md5_sum_for_file
                # TODO: Also check the previously uploaded file responses for MD5s of the same path
                else:
                    logger.debug(f"Computing new md5sum for file {path}")
                    sums[str(path)] = GofileIOUploader.checksum(path)

        # Save md5sums to local config cache so we don't have to recompute later
        self.options["config"]["history"]["md5_sums"].update(sums)
        self.save_config_file()

        return sums

    @staticmethod
    def checksum(filename: Path, hash_factory=hashlib.md5, chunk_num_blocks: int = 128):
        """
        https://stackoverflow.com/questions/1131220/get-the-md5-hash-of-big-files-in-python
        """
        h = hash_factory()
        with open(filename, "rb") as f:
            while chunk := f.read(chunk_num_blocks * h.block_size):
                h.update(chunk)
        return h.hexdigest()

    async def upload_files(self, path: str, folder: Optional[str] = None, save: bool = True) -> None:
        contents = Path(path)

        if contents.is_file():
            paths = [contents]
        else:
            paths = [x for x in contents.iterdir()]
            if folder is None:
                folder = contents.name
        folder_id = await self.get_folder_id(folder)

        if folder_id:
            folder_id_contents = await self.api.get_content(folder_id, cache=True, password=None)
            # TODO: Consider more lightweight name-only matching instead of md5sum

            md5_sums_of_items_in_folder = [
                x["md5"] for x in folder_id_contents["data"].get("children", {}).values() if x.get("type") == "file"
            ]

            paths_and_md5_sums = self.get_md5_sums_for_files(paths)
            paths_to_skip = [k for k, v in paths_and_md5_sums.items() if v in md5_sums_of_items_in_folder]

            if self.make_public and folder_id != self.api.root_folder_id and not folder_id_contents["data"]["public"]:
                logger.info(f"Making folder {folder_id} public")
                await self.api.update_content(folder_id, "public", "true")

            logger.info(
                f'{len(paths_to_skip)}/{len(paths)} files will be skipped since they were already uploaded to the folder "{folder}"'
            )
            paths = [x for x in paths if str(x) not in paths_to_skip]

        if paths:
            responses = await self.api.upload_files(paths, folder_id)
            if save and responses:
                file_name = f"gofile_upload_{int(time.time())}.csv"
                with open(file_name, "w", newline="") as csvfile:
                    logger.info(f"Saving uploaded files to {file_name}")
                    field_names = [
                        "filePath",
                        "filePathMD5",
                        "fileNameMD5",
                        "uploadSuccess",
                        "code",
                        "downloadPage",
                        "fileId",
                        "fileName",
                        "guestToken",
                        "md5",
                        "parentFolder",
                    ]
                    csv_writer = csv.DictWriter(csvfile, dialect="excel", fieldnames=field_names)
                    csv_writer.writeheader()
                    for row in responses:
                        csv_writer.writerow(row)

            else:
                pprint(responses)
        else:
            print("No file paths left to upload")


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
        gofile_client.save_config_file()


def main():
    asyncio.run(async_main())

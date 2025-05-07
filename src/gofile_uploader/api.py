import asyncio
import hashlib
import logging
import re
from pathlib import Path
from pprint import pformat

import aiohttp
from tqdm.asyncio import tqdm_asyncio
from typing_extensions import List, Literal, Optional

from .types import (
    CompletedFileUploadResult,
    CreateFolderResponse,
    DeleteContentsResponse,
    GetAccountDetailsResponse,
    GetAccountIdResponse,
    GetContentResponse,
    GetNewAccountResponse,
    GetServersResponse,
    GofileUploaderOptions,
    UpdateContentOption,
    UpdateContentOptionValue,
    UpdateContentResponse,
)
from .utils import ProgressFileReader, TqdmUpTo

logger = logging.getLogger(__name__)


class GofileIOAPI:
    def __init__(self, options: GofileUploaderOptions):
        self.options = options
        self.session_headers = (
            {"Authorization": f"Bearer {self.options['token']}"} if self.options.get("token") else None
        )
        self.session = aiohttp.ClientSession(
            "https://api.gofile.io", headers=self.session_headers, raise_for_status=True
        )
        # These are set once the account is queried
        self.root_folder_id = None
        self.account_id = None
        self.is_premium = False

        self.wt = None
        self.server_sessions = {}
        self.created_folders = {}
        self.sem = asyncio.Semaphore(self.options["connections"])

    async def init(self):
        # Create an account if none was specified
        if self.options.get("token") is None:
            temporary_account = await GofileIOAPI.get_new_account()
            self.options["token"] = temporary_account["data"]["token"]
            self.account_id = temporary_account["data"]["id"]

            # Recreate the API session with the new auth
            if not self.session.closed:
                await self.session.close()
            self.session_headers = {"Authorization": f"Bearer {self.options['token']}"}
            self.session = aiohttp.ClientSession(
                "https://api.gofile.io", headers=self.session_headers, raise_for_status=True
            )

        # Use the account provided by the token
        else:
            account_id = await self.get_account_id()
            self.account_id = account_id["data"]["id"]

        if self.wt is None:
            self.wt = await self.get_wt()

        account = await self.get_account_details(self.account_id)
        self.root_folder_id = account["data"]["rootFolder"]
        self.is_premium = account["data"]["tier"] != "standard"

    @staticmethod
    async def get_new_account() -> GetNewAccountResponse:
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.post("https://api.gofile.io/accounts") as resp:
                response = await resp.json()
                GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
                return response

    @staticmethod
    def raise_error_if_error_in_remote_response(response, exit_if_rate_limited=False):
        if response:
            if exit_if_rate_limited and ("error-rateLimit" in response.get("status", "")):
                exit(1)
            if "error" in response.get("status", "") or response.get("status", "") != "ok":
                msg = f"Failed getting response from server:\n{pformat(response)}"
                logger.error(msg)
                raise Exception(msg)

    def raise_error_if_not_premium_status(self):
        if self.is_premium is False:
            raise Exception(f"Account tier is standard but needs to be premium")

    async def get_wt(self) -> Optional[str]:
        # Maybe one day I'll figure out what this stands for
        wt = None
        async with aiohttp.ClientSession() as session:
            async with session.get("https://gofile.io/dist/js/global.js") as resp:
                response = await resp.text()
                if self.options.get("debug_save_js_locally"):
                    response_hash = hashlib.md5(response.encode("utf-8")).hexdigest()
                    file_name = Path(f"gofile-globaljs-{response_hash}.js")
                    if file_name.exists():
                        logger.debug(f"Gofile script {file_name} was retrieved but already existed locally")
                    else:
                        with open(file_name, "w") as file:
                            file.write(response)
                            logger.debug(f"Gofile script {file_name} was retrieved and saved locally")
                wt_search = re.search(r"\.wt\s*=\s*\"(?P<whitelist_token>\w{12})\"", response)
                if wt_search:
                    wt = wt_search.groupdict().get("whitelist_token")
                    logger.debug(f"Gofile wt was successfully extracted as {wt}")
                else:
                    logger.error(
                        f"⚠️💀⚠️💀⚠️💀Failed to fetch gofile whitelist token (wt), many functions are likely to FAIL!"
                    )
        return wt

    async def get_servers(self, zone: Optional[Literal["eu", "na"]]) -> GetServersResponse:
        params = {"zone": zone} if zone else None
        async with self.session.get("/servers", params=params) as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
            return response

    async def get_account_id(self) -> GetAccountIdResponse:
        async with self.session.get("/accounts/getid") as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
            logger.debug(f'Account id is "{response["data"]["id"]}"')
            return response

    async def get_account_details(self, account_id: str) -> GetAccountDetailsResponse:
        async with self.session.get(f"/accounts/{account_id}") as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
            logger.debug(f'Account details for "{account_id}" are:\n{pformat(response["data"])}')
            return response

    async def set_premium_status(self) -> None:
        account = await self.get_account_details(self.account_id)
        self.is_premium = account["data"]["tier"] != "standard"

    async def get_content(self, content_id: str, cache: Optional[bool], password: Optional[str]) -> GetContentResponse:
        # Requires Premium or the whitelist token
        if not self.wt:
            self.raise_error_if_not_premium_status()

        params = {}
        if cache is False:
            params["cache"] = "false"
        # Could also make this match against `is True` but maybe using cached responses is better
        elif cache:
            params["cache"] = "true"

        if self.wt:
            params["wt"] = self.wt
        if password:
            params["password"] = password

        async with self.session.get(f"/contents/{content_id}", params=params) as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
            return response

    async def create_folder(self, parent_folder_id: str, folder_name: Optional[str]) -> CreateFolderResponse:
        data = {"parentFolderId": parent_folder_id}
        if folder_name:
            data["folderName"] = folder_name

        logger.debug(f"Creating new folder '{folder_name}' in parent folder id '{parent_folder_id}' ")
        async with self.session.post("/contents/createfolder", data=data) as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
            logger.debug(
                f'Folder "{response["data"]["name"]}" ({response["data"]["id"]}) created in {response["data"]["parentFolder"]}'
            )
            self.created_folders[folder_name] = response["data"]
            return response

    async def update_content(
        self, content_id: str, option: UpdateContentOption, value: UpdateContentOptionValue
    ) -> UpdateContentResponse:
        data = {"attribute": option, "attributeValue": value}
        async with self.session.put(f"/contents/{content_id}/update", data=data) as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response)
            return response

    async def delete_contents(self, content_ids: list[str]) -> DeleteContentsResponse:
        data = {"contentsId": ",".join(content_ids)}
        async with self.session.delete(f"/contents", data=data) as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response)
            return response

    async def upload_file(self, file_path: Path, folder_id: Optional[str] = None) -> CompletedFileUploadResult:
        if not file_path.exists():
            raise Exception(f"File path {file_path} does not exist, cannot upload!")

        if folder_id is None:
            logger.warning(
                "Uploading files without specifying folder ID, this will upload it to a randomly name folder. You most likely do not want to do this"
            )

        file_metadata = {
            "filePath": str(file_path),
            "filePathMD5": hashlib.md5(str(file_path).encode("utf-8")).hexdigest(),
            "fileNameMD5": hashlib.md5(str(file_path.name).encode("utf-8")).hexdigest(),
            "uploadSuccess": None,
        }
        async with self.sem:
            retries = 0
            while retries < self.options["retries"]:
                try:
                    # TODO: Rate limit to one request every 10 seconds
                    servers = await self.get_servers(zone=self.options.get("zone"))

                    server = next(iter(servers["data"]["servers"]))["name"]
                    if server not in self.server_sessions:
                        logger.info(f"Using new server connection to {server}")
                        timeout = aiohttp.ClientTimeout(total=self.options["timeout"])
                        self.server_sessions[server] = aiohttp.ClientSession(
                            f"https://{server}.gofile.io",
                            headers=self.session_headers,
                            raise_for_status=True,
                            timeout=timeout,
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
                                GofileIOAPI.raise_error_if_error_in_remote_response(
                                    response, exit_if_rate_limited=False
                                )

                                file_metadata.update(response["data"])
                                file_metadata["uploadSuccess"] = response.get("status")
                                if file_metadata["uploadSuccess"] == "ok":
                                    self.options["history"]["uploads"].append(file_metadata)
                                return file_metadata

                except Exception as e:
                    retries += 1
                    logger.exception(f"Failed to upload {file_path} due to:\n", stack_info=True, exc_info=e)

                return file_metadata

    async def upload_files(self, paths: List[Path], folder_id: Optional[str] = None) -> List[CompletedFileUploadResult]:
        tasks = [self.upload_file(test_file, folder_id) for i, test_file in enumerate(paths)]
        responses = await tqdm_asyncio.gather(*tasks, desc="Files uploaded")
        return responses

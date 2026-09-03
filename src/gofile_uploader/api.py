import asyncio
import hashlib
import logging
import math
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from pprint import pformat

import aiohttp
import ua_generator
from tqdm.asyncio import tqdm_asyncio
from typing_extensions import List, Literal, Optional, deprecated
from ua_generator.options import Options

from .latest_salt import DATE, SALT
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
    UploadFileResponse,
)
from .utils import ProgressFileReader, TqdmUpTo

logger = logging.getLogger(__name__)


class GofileIOAPI:
    def __init__(self, options: GofileUploaderOptions):
        self.options = options
        # These are set once the account is queried
        self.root_folder_id = None
        self.account_id = None
        self.is_premium = False

        self.website_token_salt = None
        self.website_token_salt_fetch_time = None

        # Generate a semi random user agent, no idea how this will play out
        ua_options = Options()
        ua_options.weighted_versions = True
        user_agent = ua_generator.generate(device="desktop", options=ua_options)

        # TODO: Use the generated agent
        # self.browser_user_agent = user_agent
        self.browser_user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0"
        self.browser_language = "en-US"

        # NOTE: The headers for these save sassions also need to be updated periodically
        # Ideally at the same time that the other headers for the main session are updated
        self.server_sessions = {}
        self.created_folders = {}
        self.sem = asyncio.Semaphore(self.options["connections"])

        # In 99% of cases this salt will be out of date but give the API something to have here
        if not self.options.get("website_token_salts"):
            self.options["website_token_salts"] = {DATE: SALT}

        # These are mostly used for testing/debugging
        self.did_we_initialize = False

        # NOTE: These headers need to be updated in self.init after GofileIOAPI is created and also periodically
        # since X-WEBSITE-TOKEN changes depending on time
        self.session_headers = {
            "X-BL": self.browser_language,
            "User-Agent": self.browser_user_agent,
        }
        if self.options.get("token"):
            self.session_headers["Authorization"] = f"Bearer {self.options['token']}"

        self.session = aiohttp.ClientSession(
            "https://api.gofile.io", headers=self.session_headers, raise_for_status=True
        )

    async def init(self):
        # Get the website token salt since this does not require auth/account
        if self.website_token_salt is None:
            await self.get_website_token_salt()
            # Even though we get the salt first, we can only generate the website token once we have an account token
            # The function above also updates the class with the salt so we don't need to save it here too
            if self.website_token_salt is None:
                logger.error("Failed to get website token salt")

        # Create an account if none was specified
        if self.options.get("token") is None:
            temporary_account = await GofileIOAPI.get_new_account()
            self.options["token"] = temporary_account["data"]["token"]
            self.account_id = temporary_account["data"]["id"]

            # Recreate the API session with the new auth
            if not self.session.closed:
                await self.session.close()

            self.session_headers["Authorization"] = f"Bearer {self.options['token']}"
            self.session_headers["X-Website-Token"] = self.generate_compliant_website_token(self.options["token"])

            self.session = aiohttp.ClientSession(
                "https://api.gofile.io", headers=self.session_headers, raise_for_status=True
            )

        # Use the account provided by the token
        else:
            account_id = await self.get_account_id()
            self.account_id = account_id["data"]["id"]

        account = await self.get_account_details(self.account_id)
        self.root_folder_id = account["data"]["rootFolder"]
        # I don't know the actual value for premium, so I'm reversing the common free ones
        self.is_premium = account["data"]["tier"] == "premium"

        if not self.is_premium:
            if self.website_token_salt is None:
                raise Exception(
                    f"Free account used but whitelist token for premium features was not found. Create an issue."
                )
            # FIXME: This needs to be dynamically re-generated every 4 hours
            self.session_headers["X-Website-Token"] = self.generate_compliant_website_token(self.options["token"])
            self.session.headers["X-Website-Token"] = self.session_headers["X-Website-Token"]

        self.did_we_initialize = True

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
            if "error" in response.get("status", "") or response.get("status", "") not in ["ok", "noServer"]:
                msg = f"Failed getting response from server:\n{pformat(response)}"
                logger.error(msg)
                raise Exception(msg)

    def raise_error_if_not_premium_status(self):
        if self.is_premium is False:
            raise Exception(f"Account tier is standard but needs to be premium")

    def generate_compliant_website_token(self, salt) -> str:
        """
        Generates a compliant time sensitive website token
        This should be generated when an actual request is made

        This comes from a hashed version of:
        "browser" userAgent: Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0
        "browser" language: en-US
        input: Your account token
        timeBucket: 124120, a 4 hour time bucket
        secretSalt: 12af056dacea0b, comes from obfuscated js file on the site, not sure if this is the one that rotates
        """
        potential_account_id = self.account_id or self.options.get("token")
        if (
            potential_account_id is None
            and self.did_we_initialize is False
            and os.environ.get("GOFILE_TOKEN") is not None
        ):
            logger.info(
                "Special case for trying to get website token but for some reason the API does not have it. "
                "However it is present in the environment variables so that will be used."
            )
            potential_account_id = os.environ.get("GOFILE_TOKEN")

        if potential_account_id is None:
            raise Exception(
                "Tried to generate a website token without any account id, this should not be possible."
                "Even in anonymous mode a fresh new account id is generated."
            )

        components = [
            self.browser_user_agent,
            self.browser_language,
            potential_account_id,
            str(math.floor(time.time() / 14400)),
            salt,
        ]

        string_to_hash = "::".join(components)
        website_token = hashlib.sha256(string_to_hash.encode("utf-8")).hexdigest()
        return website_token

    async def get_website_token_salt(self) -> Optional[str]:
        """
        Get a website token directly from gofile JS files

        Historically this was just a plain token that lived in a JS file somewhere on the site
        Nowadays, it's a time based SHA256 containing basic browser info and a "website token" salt that's found in an
        obfuscated JS file from gofile

        There are also multiple versions of the JS file that can be served but so far they give the same salt

        While this function will still return a whole website token, it is now time-sensitive and as such should be generated
        on demand.
        This token needs to be in the headers under 'X-Website-Token': wt,
        and the same browser language used should also be there under 'X-BL': navigator.language

        Because I'm lazy and don't want to figure out how to extract the salt from each obfuscated versions I've decided to
        just run the damn JavaScript file and have it give me the salt.

        This to be honest seems kinda dangerous since you're running whatever js file the site gives.
        I will probably add some flags for this and also have it compare SHAs of known JS files before running the
        actual JS code as a last resort.
        """
        salt_file_contents = None
        current_date = date.today().isoformat()

        async with aiohttp.ClientSession() as session:
            async with session.get("https://gofile.io/js/wt.obf.js") as resp:
                salt_file_contents = await resp.text()
                salt_file_hash = hashlib.md5(salt_file_contents.encode("utf-8")).hexdigest()
                if self.options.get("debug_save_js_locally"):
                    file_name = Path(f"gofile-wtobfjs-{salt_file_hash}.js")
                    if file_name.exists():
                        logger.debug(f"Gofile script {file_name} was retrieved but already existed locally")
                    else:
                        with open(file_name, "w") as file:
                            file.write(salt_file_contents)
                            logger.debug(f"Gofile script {file_name} was retrieved and saved locally")

        # FIXME: TODO: After probing the JS file a bunch of times over a long enough timespan, it turns out that the
        # obfuscated file changes quite often thus producing a bunch of different file hashes, however the actual
        # salt in the file does not change
        # Because of this it doesn't make sense to try and store hashes locally or remotly
        # Instead I think it makes the most sense to store the salt and the last time the salt was updated
        # This does mean the structure here will change a bit
        #
        # TODO: Also check the settings/config from the programs previous run aka config file
        # need to remember how/when config is saved

        wt_salt = self.options["website_token_salts"].get(current_date)

        if wt_salt:
            logger.debug("Website token script hash found in local repository, salt from here will be used")
        else:
            try:
                logger.debug("Trying to find website token salt in remote repository")
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://raw.githubusercontent.com/alexmi256/gofile-uploader/refs/heads/master/src/gofile_uploader/latest_salt.py"
                    ) as resp:
                        online_salt_hashes = await resp.text()

                        latest_online_date = re.search(r"DATE = '(?P<date>\d{4}-\d{2}-\d{2})'", online_salt_hashes)
                        latest_online_salt = re.search(r"SALT = '(?P<salt>[a-fA-F0-9]+)'", online_salt_hashes)
                        if latest_online_date and latest_online_salt:
                            latest_online_date = latest_online_date.group("date")
                            latest_online_date_comparable = date.fromisoformat(latest_online_date)
                            latest_online_salt = latest_online_salt.group("salt").lower()

                            if (
                                latest_online_date_comparable >= date.today()
                                and latest_online_date not in self.options["website_token_salts"]
                            ):
                                logger.debug(
                                    f"Remote token salt date {latest_online_date_comparable} >= {current_date} (today)"
                                )
                                wt_salt = latest_online_salt
                            else:
                                logger.warning(
                                    f"Remote token salt date {latest_online_date_comparable} < {current_date} (today),"
                                    f"need to execute JavaScript in order to get today's salt"
                                )
                        else:
                            logger.exception(
                                "Online file for hashes was successfully retrieved but date and hash could not be parsed out"
                            )

            except Exception as e:
                logger.exception("Discovering latest website token salt from remote repository failed")
                logger.exception(e)

            # TODO: Add a true CLI arg for this
            ALLOW_JS_EXECUTION = True

            # Try to run the site's JS as a last resort if enabled
            if wt_salt is None and ALLOW_JS_EXECUTION:
                logger.debug("Getting website token salt by running the sites JavaScript code")
                try:
                    # Let's run random JavaScript!
                    from pythonmonkey import eval as js_eval

                    runnable_js_code = (
                        "let navigator={};" + salt_file_contents + ';function _sha256(e){return e}generateWT("test");'
                    )

                    result = js_eval(runnable_js_code)
                    wt_salt = result.split("::")[-1]

                except Exception as e:
                    logger.exception("Could not execute gofile wt.obf.js")
                    raise e
            else:
                raise Exception("Failed to fetch contents of wt.obf.js")

        self.options["website_token_salts"][current_date] = wt_salt
        self.website_token_salt = wt_salt
        self.website_token_salt_fetch_time = datetime.now()

        return wt_salt

    async def get_wt(self) -> Optional[str]:
        """
        Fetch the website token salt, format it with other required data and return the SHA256 of it
        """
        website_token_salt = await self.get_website_token_salt()
        website_token = self.generate_compliant_website_token(website_token_salt)

        return website_token

    @deprecated("GoFile API no longer mentions this endpoint in their docs")
    async def get_servers(self) -> GetServersResponse:
        """
        This endpoint appears to be deprecated and never really worked well

        As of Sept 2026 Docs metion the following servers:
        # {id: 'eu-par', host: 'upload-eu-par.gofile.io', label: 'Europe (Paris)'},
        # {id: 'na-phx', host: 'upload-na-phx.gofile.io', label: 'North America (Phoenix)'},
        # {id: 'na-nyc', host: 'upload-na-nyc.gofile.io', label: 'North America (New York City)'},
        # {id: 'ap-sgp', host: 'upload-ap-sgp.gofile.io', label: 'Asia Pacific (Singapore)'},
        # {id: 'ap-hkg', host: 'upload-ap-hkg.gofile.io', label: 'Asia Pacific (Hong Kong)'},
        # {id: 'ap-tyo', host: 'upload-ap-tyo.gofile.io', label: 'Asia Pacific (Tokyo)'},
        # {id: 'ap-syd', host: 'upload-ap-syd.gofile.io', label: 'Asia Pacific (Sydney)'},
        # {id: 'sa-sao', host: 'upload-sa-sao.gofile.io', label: 'South America (São Paulo)'},

        The endpoint however does still work and returns some of the servers mentioned above as well as others
        """
        async with self.session.get("/servers") as resp:
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

    async def get_content(
        self,
        content_id: str,
        cache: Optional[bool],
        password: Optional[str],
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_field: Optional[Literal["createTime", "name", "size", "downloads", "mimetype"]] = None,
        sort_direction: Optional[int] = None,
        content_filter: Optional[str] = None,
        max_depth: Optional[int] = None,
    ) -> GetContentResponse:
        # Requires Premium or the whitelist token
        if not self.website_token_salt:
            self.raise_error_if_not_premium_status()

        # TODO: Always update the session token if necessary before running this

        params = {}
        if cache is False:
            params["cache"] = "false"
        # Could also make this match against `is True` but maybe using cached responses is better
        elif cache:
            params["cache"] = "true"

        if password:
            params["password"] = password

        if page:
            params["page"] = page
        if page_size:
            params["pageSize"] = page_size

        if sort_field:
            params["sortField"] = sort_field
        if sort_direction:
            params["sortDirection"] = sort_direction

        if content_filter:
            params["contentFilter"] = content_filter

        if max_depth:
            params["maxDepth"] = max_depth

        async with self.session.get(f"/contents/{content_id}", params=params) as resp:
            response = await resp.json()
            GofileIOAPI.raise_error_if_error_in_remote_response(response, exit_if_rate_limited=True)
            return response

    async def create_folder(
        self, parent_folder_id: str, folder_name: Optional[str], public: Optional[bool] = None
    ) -> CreateFolderResponse:
        data = {"parentFolderId": parent_folder_id}
        if folder_name:
            data["folderName"] = folder_name
        if public is not None:
            data["public"] = public

        logger.debug(f"Creating new folder '{folder_name}' in parent folder id '{parent_folder_id}' ")
        async with self.session.post("/contents/createFolder", data=data) as resp:
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
            "response": None,
        }
        async with self.sem:
            retries = 0
            while retries < self.options["retries"]:
                try:
                    server_name = self.options.get("zone", "upload")

                    if server_name not in self.server_sessions:
                        logger.info(f"Using new server connection to {server_name}")
                        timeout = aiohttp.ClientTimeout(total=self.options["timeout"])
                        self.server_sessions[server_name] = aiohttp.ClientSession(
                            f"https://{server_name}.gofile.io",
                            headers=self.session_headers,
                            raise_for_status=True,
                            timeout=timeout,
                        )

                    session = self.server_sessions[server_name]

                    # I couldn't get CallbackIOWrapper to work due to "Can not serialize value type: <class 'tqdm.utils.CallbackIOWrapper'>"
                    # Maybe someone can try and get better results
                    with TqdmUpTo(unit="B", unit_scale=True, unit_divisor=1024, miniters=1, desc=file_path.name) as t:
                        with ProgressFileReader(filename=file_path, read_callback=t.update_to) as upload_file:
                            # FIXME: I cannot figure out this Unicode BS
                            # Via browser uploading non-ascii chars works just fine and the file name does not appear to
                            # be encoded in anything special.
                            # If I copy the request as cURL I see that file name will be encoded like "\u7f8e\u306e"
                            # When I ran the cURL this uploaded just fine and the response I got back was 美」which is correct
                            # I tried `FormData(charset=utf-8|ascii)` as well using `file_path.name.encode('unicode_escape').decode('ascii')`
                            # and none of this worked.
                            # At this time I am out of ideas for a proper fix.
                            data = aiohttp.FormData()
                            formatted_file_name = file_path.name
                            data.add_field("file", upload_file, filename=formatted_file_name)
                            logger.debug(f'File "{file_path.name}" was selected for upload')
                            if folder_id:
                                logger.debug(f'File {file_path.name} will be uploaded to folder id "{folder_id}"')
                                data.add_field("folderId", folder_id)
                            else:
                                logger.debug(
                                    f"File {file_path.name} will be uploaded to a new randomly created folder id"
                                )

                            async with session.post("/contents/uploadfile", data=data) as resp:
                                file_metadata["response"]: UploadFileResponse = await resp.json()
                                GofileIOAPI.raise_error_if_error_in_remote_response(
                                    file_metadata["response"], exit_if_rate_limited=False
                                )

                                if file_metadata["response"].get("status") == "ok":
                                    # Hacky way of dealing with the Unicode filename issue #17
                                    if file_metadata["response"]["data"]["name"] != file_path.name:
                                        # Rename the file we just uploaded which is a HACK
                                        logger.debug(
                                            f'Renaming file on server "{file_metadata['response']["data"]["name"]}" to {file_path.name} due to Unicode being hard to deal with'
                                        )
                                        try:
                                            renamed_file_response = await self.update_content(
                                                file_metadata["response"]["data"]["id"], "name", file_path.name
                                            )
                                            file_metadata["response"]["data"]["name"] = renamed_file_response["data"][
                                                "name"
                                            ]
                                        except Exception as rename_error:
                                            logger.exception(
                                                "Rename for unicode based file name failed. Content still successfully uploaded but its name may look off.",
                                                exc_info=rename_error,
                                            )
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

import asyncio
import csv
import hashlib
import json
import logging
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from pprint import pformat, pprint

from tqdm import tqdm
from typing_extensions import List, Optional, cast

from .api import GofileIOAPI
from .cli import cli
from .types import CompletedFileUploadResult, GofileUploaderOptions
from .utils import return_dict_without_none_value_keys

logger = logging.getLogger(__name__)


class GofileIOUploader:
    def __init__(self, options: GofileUploaderOptions):
        self.options = options
        self.api = GofileIOAPI(options)

    # TODO: Consider doing init in client instead of API

    def save_config_file(self):
        """
        Creates the config example_files and file with the current config options if using config is enabled
        """
        if self.options.get("use_config"):
            config_directory = self.options["config_directory"]
            config_file_path = self.options["config_file_path"]
            if not config_directory.exists():
                logger.info(f"Creating config example_files at {config_directory}")
                config_directory.mkdir(parents=True, exist_ok=True)

            with open(config_file_path, "w") as config_file:
                logger.debug(f"Saving config to {config_file_path}")

                # Only GofileUploaderLocalConfigOptions should be saved locally because the other ones don't make sense
                # to save
                config_history = {
                    "md5_sums": self.options.get("history", {}).get("md5_sums", {}),
                    "uploads": self.options.get("history", {}).get("uploads", []),
                }
                savable_config = {
                    "token": self.options.get("token"),
                    "zone": self.options.get("zone"),
                    "connections": self.options.get("connections"),
                    "public": self.options.get("public"),
                    "save": self.options.get("save"),
                    "log_file": str(self.options.get("log_file")),
                    "log_level": self.options.get("log_level"),
                    "timeout": self.options.get("timeout"),
                    "retries": self.options.get("retries"),
                    "recurse_directories": self.options.get("recurse_directories"),
                    "recurse_max": self.options.get("recurse_max"),
                    "history": config_history,
                }
                logger.debug(pformat(savable_config))
                config = return_dict_without_none_value_keys(savable_config)
                json.dump(config, config_file, indent=2)
        else:
            logger.warning(f"Config file is not in use, will not save locally")

    async def get_folder_id(self, folder: Optional[str], cache: bool = True) -> str:
        """
        Get the id of a folder's name
        A folder should be the name of the folder you want to retrieve the id of but can also be the root id
        """
        # No folder provided, use root folder (account now always exists since it will create one if none provided)
        if folder is None:
            logger.info("No folder was specified, root folder id will be used")
            return self.api.root_folder_id
        # Folder is UUIDv4, assume user is referencing to something already created
        elif re.match(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", folder):
            logger.warning(
                "For some reason the given folder name to create was a UUID so we will assume it already exists"
            )
            return folder
        # Folder needs to be created or already exists
        else:
            root_folder_contents = await self.api.get_content(self.api.root_folder_id, cache=cache, password=None)

            # Another case that tbh don't make much sense but the user might specify "root" folder name which
            # is usually the root folder name
            if root_folder_contents["data"]["name"] == folder:
                logger.info("The folder we wanted to create ended up being the account root folder")
                return cast(str, root_folder_contents["data"]["id"])

            # Check in the root folder if there is a example_files with that name already
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
                # We couldn't find a previously created folder with the same name so we should create a new one
                logger.info(
                    f'Could not find a folder inside the root folder with the name "{folder}" so we will create one'
                )
                if self.options["dry_run"]:
                    print(
                        f"Dry run only, skipping folder creation of '{folder}' and using root folder '{self.api.root_folder_id}'"
                    )
                    return self.api.root_folder_id
                else:
                    new_folder = await self.api.create_folder(self.api.root_folder_id, folder)
                    return new_folder["data"]["id"]

    async def cleanup_api_sessions(self):
        await self.api.session.close()
        for server_session in self.api.server_sessions.values():
            await server_session.close()
        self.api.server_sessions.clear()

    @staticmethod
    def save_responses_to_csv(responses: List[CompletedFileUploadResult]):
        created_time = datetime.now().isoformat()
        file_name = f"gofile_upload_{created_time.replace(':','.')}.csv"
        with open(file_name, "w", newline="") as csvfile:
            logger.info(f"Saving uploaded files to {file_name}")
            field_names = list(set().union(*[x.keys() for x in responses if x]))
            csv_writer = csv.DictWriter(csvfile, dialect="excel", fieldnames=field_names)
            csv_writer.writeheader()
            for row in responses:
                csv_writer.writerow(row)

    def get_md5_sums_for_files(self, paths: List[Path]) -> dict[str, str]:
        paths_of_files = [x for x in paths if x.is_file() and str(x) not in self.options["history"]["md5_sums"]]

        sums = {}

        disable_hashing_progress = True if len(paths_of_files) < 50 else False

        number_of_files = len(paths_of_files)

        if number_of_files:
            logger.info(f"Calculating hashes for {number_of_files}/{len(paths)} files")
        else:
            logger.info(f"All {len(paths)} files were previously hashed")

        with tqdm(
            total=number_of_files, desc="Hashes Calculated", disable=disable_hashing_progress
        ) as files_hashed_progress:
            with ProcessPoolExecutor(max_workers=self.options["hash_pool_size"]) as executor:
                futures = {executor.submit(GofileIOUploader.checksum, arg): arg for arg in paths_of_files}
                for future in as_completed(futures):
                    arg = futures[future]
                    sums[str(arg)] = future.result()
                    files_hashed_progress.update(1)

        # Save md5sums to local config cache so we don't have to recompute later
        self.options["history"]["md5_sums"].update(sums)
        # Update the current configs since we could have calculated md5 sums
        self.save_config_file()

        return {str(path): self.options["history"]["md5_sums"][str(path)] for path in paths}

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

    async def upload_files(self, path: Path, folder: Optional[str] = None) -> None:
        if path.is_file():
            paths = [path]
        else:
            if self.options.get("recurse_directories"):
                max_files_before_error = self.options["recurse_max"]
                paths = [x for x in path.rglob("*") if x.is_file()]
                if len(paths) > max_files_before_error:
                    raise Exception(
                        f'You are about to upload {len(paths)} files which is a lot. Are you sure you want to do this? If yes run again with the "--recurse-max={len(paths)}" flag.'
                    )
            else:
                paths = [x for x in path.iterdir()]

            if self.options.get("exclude_file_types"):
                paths = [x for x in paths if x.suffix[1:] not in self.options.get("exclude_file_types").split(",")]

            if self.options.get("only_file_types"):
                paths = [x for x in paths if x.suffix[1:] in self.options.get("only_file_types").split(",")]

            if folder is None:
                folder = path.name
        folder_id = await self.get_folder_id(folder)
        paths_to_skip = []
        renamed_files = []

        # In the current state, a folder id should almost always exist because we're now creating accounts on init
        # if one was not provided
        if folder_id:
            folder_id_contents = await self.api.get_content(folder_id, cache=True, password=None)

            md5_sums_of_items_in_folder = [
                x["md5"] for x in folder_id_contents["data"].get("children", {}).values() if x.get("type") == "file"
            ]

            paths_and_md5_sums = self.get_md5_sums_for_files(paths)

            # Check which items should be skipped by checking their local and remote server md5sums
            for local_file_path, local_file_md5sum in paths_and_md5_sums.items():
                if local_file_md5sum in md5_sums_of_items_in_folder:
                    paths_to_skip.append(local_file_path)

            if (
                self.options["public"]
                and folder_id != self.api.root_folder_id
                and not folder_id_contents["data"]["public"]
            ):
                logger.info(f"Making folder {folder_id} public")
                if self.options["dry_run"]:
                    print(f"Dry run only, folder {folder_id} will not be made public")
                else:
                    await self.api.update_content(folder_id, "public", "true")

            skipped_files_msg = f'{len(paths_to_skip)}/{len(paths)} files will be skipped since they were already uploaded to the folder "{folder}" ({folder_id})'

            logger.info(skipped_files_msg)

            if len(paths_to_skip):
                print(skipped_files_msg)

            paths = [x for x in paths if str(x) not in paths_to_skip]

            if self.options["rename_existing"]:
                # Here begins the code for renaming existing (matched by md5sum) files
                for existing_file in paths_to_skip:
                    existing_file_md5 = paths_and_md5_sums[existing_file]
                    existing_file_name = Path(existing_file).name
                    # Technically multiple copies of the same file could be uploaded and need renaming
                    matching_remote_files_to_rename = [
                        x
                        for x in folder_id_contents["data"].get("children", {}).values()
                        if x.get("type") == "file"
                        and x.get("md5") == existing_file_md5
                        and existing_file_name != x["name"]
                    ]

                    if matching_remote_files_to_rename:
                        logger.debug(
                            f"File {existing_file} matched against md5 {existing_file_md5} on the server but with different name. Will renamed."
                        )

                    if self.options["dry_run"]:
                        print(f"Dry run only, file renaming will be skipped")
                    else:
                        for content_to_rename in matching_remote_files_to_rename:
                            logger.info(
                                f'Renaming {content_to_rename["name"]} (server) to {existing_file_name} (local)'
                            )
                            try:
                                await self.api.update_content(content_to_rename["id"], "name", existing_file_name)
                                logger.info(f'Renamed {content_to_rename["name"]} to {existing_file_name}')
                                time.sleep(0.5)
                            except Exception as e:
                                msg = f'Failed to rename file from {content_to_rename["name"]} (server) to {existing_file_name} (local)'
                                logger.exception(msg, exc_info=e, stack_info=True)

                            renamed_files.append(content_to_rename)

        renamed_files_msg = f"Renamed {len(renamed_files)}/{len(paths_to_skip)} skipped files"

        logger.info(renamed_files_msg)

        if len(renamed_files):
            print(renamed_files_msg)

        if paths:
            try:
                if self.options["dry_run"]:
                    print(f"Dry run only, files will not be uploaded")
                    responses = []
                else:
                    responses = await self.api.upload_files(paths, folder_id)
            finally:
                # FIXME: Should session management even be done here, probably not?
                await self.cleanup_api_sessions()

            if self.options.get("save") and responses:
                self.save_responses_to_csv(responses)
            else:
                pprint(responses)
        else:
            print("No file paths left to upload. Were all files already uploaded to the server?")


async def async_main() -> None:
    options = cli(sys.argv[1:])

    logging_level = getattr(logging, options["log_level"].upper())
    handlers = [logging.StreamHandler()]
    if options["log_file"]:
        logger.debug(f'Program logs will also be output to {options["log_file"]}')
        file_logger = logging.FileHandler(options["log_file"], encoding="utf-8", mode="w")
        handlers.append(file_logger)

    logging.basicConfig(level=logging_level, handlers=handlers, format="%(asctime)s " + logging.BASIC_FORMAT)

    logger.debug(pformat(options))

    gofile_client = GofileIOUploader(options)

    try:
        await gofile_client.api.init()
        await gofile_client.upload_files(options["file"], options.get("folder"))
    finally:
        await gofile_client.cleanup_api_sessions()
        gofile_client.save_config_file()


def main():
    asyncio.run(async_main())

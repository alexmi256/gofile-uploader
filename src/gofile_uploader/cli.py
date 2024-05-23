import argparse
import json
import logging
import os
from pathlib import Path

from .types import GofileUploaderLocalConfigOptions, GofileUploaderOptions

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def load_config_file(config_file_path: Path) -> GofileUploaderLocalConfigOptions:
    """
    Loads the local config file, options with None values will be omitted
    """
    config = {}
    if config_file_path.exists():
        with open(config_file_path, "r") as config_file:
            logger.debug(f"Loading config from {config_file_path}")
            try:
                loaded_config = json.load(config_file)
                config = {k: v for k, v in loaded_config.items() if v is not None}
            except Exception:
                logger.exception(f"Failed to load config file {config_file_path} as a JSON config")
    else:
        logger.error(f"Could not load config file {config_file_path} because it did not exist")
    return config


def cli() -> GofileUploaderOptions:
    parser = argparse.ArgumentParser(prog="gofile-upload", description="Gofile.io Uploader supporting parallel uploads")
    parser.add_argument("file", type=Path, help="File or directory to look for files in to upload")
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

    loaded_options = {}

    combined_options: GofileUploaderOptions = {"config_file_path": None, "config_directory": None}  # type: ignore

    # Load any local configs
    if args.use_config:
        home_path = Path.home()
        config_directory = home_path.joinpath(".config", "gofile-upload")
        config_file_path = config_directory.joinpath("config.json")
        # TODO: Might need to remove any keys where values are none
        loaded_options = load_config_file(config_file_path)
        combined_options["config_file_path"] = config_file_path
        combined_options["config_directory"] = config_directory

    # Load the CLI configs
    cli_options = vars(args)

    # Overwrite with local
    combined_options.update(loaded_options)
    # Overwrite with cli
    combined_options.update(cli_options)

    return combined_options

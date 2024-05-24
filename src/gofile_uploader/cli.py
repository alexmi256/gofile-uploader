import argparse
import json
import logging
import os
from pathlib import Path

from .types import GofileUploaderLocalConfigOptions, GofileUploaderOptions
from .utils import return_dict_without_none_value_keys

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def load_config_file(config_file_path: Path) -> GofileUploaderLocalConfigOptions:
    """
    Loads the local config file, options with None values will be omitted
    """
    config = {}
    logger.debug(f"Local config path specified as {config_file_path}")
    if config_file_path.exists():
        logger.debug(f"Loading config from {config_file_path}")
        with open(config_file_path, "r") as config_file:

            try:
                loaded_config = json.load(config_file)
                config = {k: v for k, v in loaded_config.items() if v is not None}
            except Exception:
                logger.exception(f"Failed to load config file {config_file_path} as a JSON config")
    else:
        logger.error(f"Could not load config file {config_file_path} because it did not exist")
    return return_dict_without_none_value_keys(config)


def cli() -> GofileUploaderOptions:

    # These are options that the CLI will default to when they have the BooleanOptionalAction action.
    # We do this because BooleanOptionalAction has 3 states of None/True/False which we need for the None value
    # as using store_true/store_false actions would prevent the local config from ever overriding the CLI
    default_cli_options = {
        "connections": 6,
        "public": False,
        "retries": 3,
        "save": True,
        "debug_save_js_locally": False,
    }
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
        help=f"Debug option to save the retrieved js file locally. (default: {default_cli_options['debug_save_js_locally']})",
    )
    parser.add_argument(
        "-c",
        "--connections",
        type=int,
        help=f"Maximum parallel uploads to do at once. (default: {default_cli_options['connections']})",
    )
    parser.add_argument(
        "--public",
        action=argparse.BooleanOptionalAction,
        help=f"Make all files uploaded public. By default they are private and not unsharable. (default: {default_cli_options['public']})",
    )
    parser.add_argument(
        "--save",
        action=argparse.BooleanOptionalAction,
        help=f"Don't save uploaded file urls to a \"gofile_upload_<unixtime>.csv\" file. (default: {default_cli_options['save']})",
    )
    parser.add_argument(
        "--use-config",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=f"Whether to create and use a config file in $HOME/.config/gofile_upload/config.json.",
    )
    parser.add_argument(
        "-r",
        "--retries",
        type=int,
        help=f"How many times to retry a failed upload. (default: {default_cli_options['retries']})",
    )
    args = parser.parse_args()

    loaded_options = {}

    combined_options: GofileUploaderOptions = {  # type: ignore
        "config_file_path": None,
        "config_directory": None,
        "history": {
            "md5_sums": {},
            "uploads": [],
        },
    }

    # Load the faked CLI default options first
    combined_options.update(default_cli_options)

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
    cli_options = return_dict_without_none_value_keys(vars(args))

    # Overwrite with local
    combined_options.update(loaded_options)
    # Overwrite with cli
    combined_options.update(cli_options)

    return combined_options

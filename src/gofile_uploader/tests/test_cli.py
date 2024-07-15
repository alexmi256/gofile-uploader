from pathlib import Path
from pprint import pprint
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from src.gofile_uploader.cli import cli, load_config_file
from src.gofile_uploader.types import GofileUploaderOptions


class TestClientCLI:
    def test_load_config_enabled_but_missing(self):
        config_name = Path(f"config_{uuid4()}.json")
        loaded_config = load_config_file(config_name)
        assert len(loaded_config) == 0

    def test_cli_defaults(self):
        args = ["src/gofile_uploader/tests/example_files/file1.txt", "--no-use-config", "--token=123"]
        default_options = cli(args)
        assert default_options

        response_validator = TypeAdapter(GofileUploaderOptions)

        try:
            # This is a pain to debug because exception messages get cutoff
            response_validator.validate_python(default_options, strict=True, from_attributes=True)
        except ValidationError as exc:
            pprint(repr(exc.errors()))
            raise exc

        assert default_options["config_file_path"] is None
        assert default_options["config_directory"] is None
        assert default_options["connections"] == 6
        assert default_options["public"] is False
        assert default_options["retries"] == 3
        assert default_options["save"] is True
        assert default_options["debug_save_js_locally"] is False
        assert default_options["rename_existing"] is True
        assert default_options["log_level"] == "warning"
        assert default_options["timeout"] == 600
        assert default_options["file"] == Path("src/gofile_uploader/tests/example_files/file1.txt")
        assert default_options["dry_run"] is False
        assert default_options["use_config"] is False

        assert default_options["history"]
        assert "md5_sums" in default_options["history"]
        assert "uploads" in default_options["history"]
        assert not default_options["history"]["md5_sums"]
        assert not default_options["history"]["uploads"]

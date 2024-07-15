# GofileIO Uploader
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/GofileIOUploader) ![PyPI - Version](https://img.shields.io/pypi/v/GofileIOUploader)

A python script to upload files or directories to Gofile.io
Built using `asyncio`, `aiohttp`, and `tqdm`

## Supports
- Gofile accounts
- Private and public directory uploads
- Parallel uploads
- Retries
- Progress bars
- Upload logging
- Skipping duplicate uploads
- Local configs

## Usage
1. `pip install GofileIOUploader`

```
usage: gofile-upload [-h] [-t TOKEN] [-z {na,eu}] [-f FOLDER] [-d]
                     [--debug-save-js-locally | --no-debug-save-js-locally]
                     [--rename-existing | --no-rename-existing]
                     [-c CONNECTIONS] [--timeout TIMEOUT]
                     [--public | --no-public] [--save | --no-save]
                     [--use-config | --no-use-config] [-r RETRIES]
                     [--log-level {debug,info,warning,error,critical}]
                     [--log-file LOG_FILE]
                     file

Gofile.io Uploader supporting parallel uploads

positional arguments:
  file                  File or directory to look for files in to upload

optional arguments:
  -h, --help            show this help message and exit
  -t TOKEN, --token TOKEN
                        API token for your account so that you can upload to a
                        specific account/folder. You can also set the
                        GOFILE_TOKEN environment variable for this
  -z {na,eu}, --zone {na,eu}
                        Server zone to prefer uploading to
  -f FOLDER, --folder FOLDER
                        Folder to upload files to overriding the directory
                        name if used
  -d, --dry-run         Don't create folders or upload files
  --debug-save-js-locally, --no-debug-save-js-locally
                        Debug option to save the retrieved js file locally.
                        (default: False)
  --rename-existing, --no-rename-existing
                        If a file is already found on the remote server but
                        the names differ, rename the file to its local name.
                        (default: True)
  -c CONNECTIONS, --connections CONNECTIONS
                        Maximum parallel uploads to do at once. (default: 6)
  --timeout TIMEOUT     Number of seconds before aiohttp times out. If a
                        single upload exceed this time it will fail. This will
                        depend on internet speed but in best case scenario 5GB
                        requires 300s. (default: 600)
  --public, --no-public
                        Make all files uploaded public. By default they are
                        private and not unsharable. (default: False)
  --save, --no-save     Don't save uploaded file urls to a
                        "gofile_upload_<unixtime>.csv" file. (default: True)
  --use-config, --no-use-config
                        Whether to create and use a config file in
                        $HOME/.config/gofile_upload/config.json. (default:
                        True)
  -r RETRIES, --retries RETRIES
                        How many times to retry a failed upload. (default: 3)
  --log-level {debug,info,warning,error,critical}
                        Log level. (default: warning)
  --log-file LOG_FILE   Additional file to log information to. (default: None)

```
## Details
### Duplicate Files
If you try to upload a file and it already exists then the upload will be skipped. This comparison is based on MD5 sums,
This check is based on the account being used. You can upload the same file twice to an account if different directories were specified.

### History
Configs are stored in `$HOME/.config/gofile_upload/config.json` and all successful uploads and md5 sum hashes will be saved in there.
Each time you complete an upload a `gofile_upload_<timestamp>.csv` will be created with the items uploaded and the following metadata:
`filePath,filePathMD5,fileNameMD5,uploadSuccess,code,downloadPage,fileId,fileName,guestToken,md5,parentFolder`

### Local Configuration
A local configuration can be used when you specify the `--use-config` flag
This config is saved in `$HOME/.config/gofile-upload/config.json` and contains the following options:
```json
{
  "token": "Optional[str]",
  "zone": "Optional[str]",
  "connections": "Optional[int]",
  "public": "Optional[bool]",
  "save": "Optional[bool]",
  "retries": "Optional[int]",
  "history": {
    "md5_sums": {
      "<filepath>": "<md5sum of file>"
    },
    "uploads": [
      "<upload response>"
    ]
  }
}
```
This config is loaded at runtime and combined with CLI options and defaults to make one config for the program.
The precedence for this is:
1. CLI Defaults
   - connections: 6
   - public: False
   - retries: 3
   - save: True
   - debug_save_js_locally: False
   - use_config: True
2. Local Config
3. CLI Options

The config will be saved when MD5 sums are calculated for files as well as when uploads are completed.
Configs that have a value of `None` will be omitted.

If you specify `--no-use-config` the local file will not be loaded and will not be saved to.

## Examples
Given
```
directory/
├── sample2.mkv
└── sample.mkv
```
**Upload single file anonymously** 
The file will be private

`gofile-upload directory/sample.mkv`

**Upload single file to your account and make it public**

`gofile-upload --token 123 --public directory/sample.mkv`

**Upload single file to directory `foo` in your account and make it public**

`gofile-upload --token 123 --public --folder foo directory/sample.mkv`

**Upload directory to your account and make them public**

`gofile-upload --token 123 --public directory`

**Upload directory to directory `foo` in your account and make them public**

`gofile-upload --token 123 --public --folder foo directory`

# Development
## Optional Prerequesites
- tk `sudo pacman -S base-devel tk`
- [pyenv](https://github.com/pyenv/pyenv?tab=readme-ov-file#set-up-your-shell-environment-for-pyenv)
- [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv?tab=readme-ov-file#installing-as-a-pyenv-plugin)

```bash
pyenv install 3.9
```

## Setup
```bash
pip install -r requirements-dev.txt
pre-commit install
```

## Packaging
This package currently uses [just](https://github.com/casey/just which is a Makefile like utility.

You must install `just` first and then you can do things like `just build` or `just release` which depend on the `justfile` to take actions.

# Testing
**WARNING:** Tests will use a gofile account and are destructive (they will delete all created files). 
Do not use your regular account for tests and be careful of running tests in the same environment if a `GOFILE_TOKEN` environment variable exists.

This packages uses [pytest](https://docs.pydantic.dev/latest/) and [pytest-asyncio](https://pytest-asyncio.readthedocs.io/en/latest/) for testing.
In order to omit different pytest async decorators, pytest has its configuration setup in `pyproject.toml` to
```
[tool.pytest.ini_options]
asyncio_mode = "auto"
```
In practice this is of little value because pytest-asyncio seems to be [a mess](https://github.com/pytest-dev/pytest-asyncio/issues/706) when working with fixtures at different scopes. 
I've ended up setting all fixtures and tests to session based levels even when it does not make sense but at least this does work.

It also makes use of [pydantic](https://docs.pytest.org) in order to try and validate that certain server responses match the TypedDicts I've setup.
If there is a better way to do this please let me know or draft a PR.

You should set the gofile token in your environment so that new accounts are not created for each test.
This can be done via something like `export GOFILE_TOKEN=123` or your IDE.

To test you can run the following from the root directory:
```
(venv) [alex@xyz gofile-uploader]$ pytest src/gofile_uploader
============================ test session starts ============================
platform linux -- Python 3.9.18, pytest-8.2.2, pluggy-1.5.0
rootdir: /home/alex/PycharmProjects/gofile-uploader
configfile: pyproject.toml
plugins: asyncio-0.23.7
asyncio: mode=auto
collected 3 items                                                           

src/gofile_uploader/tests/test_api_servers.py ..                      [ 66%]
src/gofile_uploader/tests/test_api_wt.py .                            [100%]

============================= 3 passed in 1.05s =============================
```

## Coverage
Test coverage is also generated using [pytest-cov](https://github.com/pytest-dev/pytest-cov).
You should disable this when debugging.


# Improvements Wishlist
- [ ] Paid accounts support, I don't have a paid account so I can't test
- [ ] Add more tests
- [ ] Recursive directory upload support

# Thanks
- https://stackoverflow.com/questions/68690141/how-to-show-progress-on-aiohttp-post-with-both-form-data-and-file
- https://github.com/londarks/Unofficial-gofile.io-API-Documentation
- https://github.com/Samridh212/File_Uploader_goFile
- https://gofile.io/api
- https://github.com/rkwyu/gofile-dl
- https://stackoverflow.com/questions/1131220/get-the-md5-hash-of-big-files-in-python
- https://packaging.python.org/en/latest/tutorials/packaging-projects/
- https://github.com/f-o
- https://stackoverflow.com/questions/66665336/validate-python-typeddict-at-runtime
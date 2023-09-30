# GofileIO Uploader

A python script to upload files or directories to Gofile.io
Built using `asyncio`, `aiohttp`, and `tqdm`

## Supports
- Gofile accounts
- Private and public directory uploads
- Parallel uploads
- Retries
- Progress bars
- Upload logging

## Usage
1. Make sure you're using python 3.8+
2. Download the script from `src/gofile_uploader/main.py`
3. Ensure you have `tqdm` and `aiohttp` packages in your python environment

```
usage: GofileIOUploader [-h] [-t TOKEN] [-f FOLDER] [-c CONNECTIONS] [--public | --no-public] [--save | --no-save] file

Gofile.io Uploader supporting parallel uploads

positional arguments:
  file                  File or directory to look for files in to upload

options:
  -h, --help            show this help message and exit
  -t TOKEN, --token TOKEN
                        API token for your account so that you can upload to a specific account/folder. You can also set the GOFILE_TOKEN environment variable for this
  -f FOLDER, --folder FOLDER
                        Folder to upload files to overriding the directory name if used
  -c CONNECTIONS, --connections CONNECTIONS
                        Maximum parallel uploads to do at once
  --public, --no-public
                        Make all files uploaded public. By default they are private and not unsharable (default: False)
  --save, --no-save     Don't save uploaded file urls to a "gofile_upload_<unixtime>.json" file (default: True)

```
## Examples
Given
```
directory/
├── sample2.mkv
└── sample.mkv
```
**Upload single file anonymously**

`python3 main.py directory/sample.mkv`

**Upload single file to your account**

`python3 main.py --token 123 foo directory/sample.mkv`

**Upload single file to directory `foo` in your account**

`python3 main.py --token 123 --folder foo directory/sample.mkv`

**Upload directory to your account**

`python3 main.py --token 123 directory`

**Upload directory to directory `foo` in your account**

`python3 main.py --token 123 --folder foo directory`

## Improvements Wishlist
- [ ] Installable packaging
- [ ] Paid accounts support
- [ ] Code cleanup

# Thanks
- https://stackoverflow.com/questions/68690141/how-to-show-progress-on-aiohttp-post-with-both-form-data-and-file
- https://github.com/londarks/Unofficial-gofile.io-API-Documentation
- https://github.com/Samridh212/File_Uploader_goFile
- https://gofile.io/api
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
- Skipping duplicate uploads

## Usage
1. `pip install GofileIOUploader`

```
usage: gofile-upload [-h] [-t TOKEN] [-z {na,eu}] [-f FOLDER] [-d]
                     [--debug-save-js-locally | --no-debug-save-js-locally]
                     [-c CONNECTIONS] [--public | --no-public]
                     [--save | --no-save] [--use-config | --no-use-config]
                     [-r RETRIES]
                     file

Gofile.io Uploader supporting parallel uploads

positional arguments:
  file                  File or directory to look for files in to upload

options:
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
                        Debug option to save the retrieved js file locally
  -c CONNECTIONS, --connections CONNECTIONS
                        Maximum parallel uploads to do at once
  --public, --no-public
                        Make all files uploaded public. By default they are
                        private and not unsharable
  --save, --no-save     Don't save uploaded file urls to a
                        "gofile_upload_<unixtime>.csv" file
  --use-config, --no-use-config
                        Whether to create and use a config file in
                        $HOME/.config/gofile_upload/config.json
  -r RETRIES, --retries RETRIES
                        How many times to retry a failed upload

```
## Details
### Duplicate Files
If you try to upload a file and it already exists then the upload will be skipped. This comparison is based on MD5 sums,
This check is based on the account being used. You can upload the same file twice to an account if different directories were specified.

### History
Configs are stored in `$HOME/.config/gofile_upload/config.json` and all successful uploads and md5 sum hashes will be saved in there.
Each time you complete an upload a `gofile_upload_<timestamp>.csv` will be created with the items uploaded and the following metadata:
`filePath,filePathMD5,fileNameMD5,uploadSuccess,code,downloadPage,fileId,fileName,guestToken,md5,parentFolder`

## Examples
Given
```
directory/
├── sample2.mkv
└── sample.mkv
```
**Upload single file anonymously**

`gofile-upload directory/sample.mkv`

**Upload single file to your account**

`gofile-upload --token 123 foo directory/sample.mkv`

**Upload single file to directory `foo` in your account**

`gofile-upload --token 123 --folder foo directory/sample.mkv`

**Upload directory to your account**

`gofile-upload --token 123 directory`

**Upload directory to directory `foo` in your account**

`gofile-upload --token 123 --folder foo directory`

# Packaging

# Improvements Wishlist
- [ ] Paid accounts support, I don't have a paid account so I can't test
- [ ] Add tests
- [ ] Add github runners for tests
- [ ] Recursive directory upload support

# Thanks
- https://stackoverflow.com/questions/68690141/how-to-show-progress-on-aiohttp-post-with-both-form-data-and-file
- https://github.com/londarks/Unofficial-gofile.io-API-Documentation
- https://github.com/Samridh212/File_Uploader_goFile
- https://gofile.io/api
- https://github.com/rkwyu/gofile-dl
- https://stackoverflow.com/questions/1131220/get-the-md5-hash-of-big-files-in-python
from pathlib import Path

from typing_extensions import (
    Literal,
    NotRequired,
    Optional,
    TypeAlias,
    TypedDict,
    Union,
)


class ServerResponse(TypedDict):
    status: str


class GetNewAccountData(TypedDict):
    id: str
    token: str


class GetNewAccountResponse(ServerResponse):
    data: GetNewAccountData


class CreateFolderData(TypedDict):
    folderId: str
    type: str
    name: str
    parentFolder: str
    createTime: int
    # childs: list[str]
    code: str


class CreateFolderResponse(ServerResponse):
    data: CreateFolderData


class GetServersServer(TypedDict):
    name: str
    zone: str


class GetServersData(TypedDict):
    servers: list[GetServersServer]


class GetServersResponse(ServerResponse):
    data: GetServersData


class GetAccountDetailsStatsCurrentData(TypedDict):
    fileCount: int
    folderCount: int
    storage: int


class GetAccountDetailsData(TypedDict):
    id: str
    email: str
    tier: str
    token: str
    rootFolder: str
    statsCurrent: GetAccountDetailsStatsCurrentData
    # filesCount: int
    # total30DDLTraffic: int
    # credit: int
    # currency: str
    # currencySign: str


class GetAccountDetailsResponse(ServerResponse):
    data: GetAccountDetailsData


class GetAccountIdData(TypedDict):
    id: str


class GetAccountIdResponse(ServerResponse):
    data: GetAccountIdData


class GetContentChildFile(TypedDict):
    isOwner: bool
    id: str
    parentFolder: str
    type: Literal["folder", "file"]
    name: str
    createTime: int
    size: int
    downloadCount: int
    md5: str
    mimetype: str
    servers: list[str]
    serverSelected: str
    link: str
    thumbnail: NotRequired[str]


class GetContentChildFolder(TypedDict):
    id: str
    type: Literal["folder", "file"]
    name: str
    code: str
    createTime: int
    public: bool
    childrenIds: list[str]


class GetFolderContentData(TypedDict):
    isOwner: bool
    id: str
    type: Literal["folder", "file"]
    name: str
    createTime: int
    parentFolder: str
    code: str
    public: bool
    totalDownloadCount: int
    totalSize: int
    childrenIds: list[str]
    children: dict[str, Union[GetContentChildFile, GetContentChildFolder]]
    # Only for root folder AFAICT
    isRoot: NotRequired[bool]


GetFileContentData: TypeAlias = GetContentChildFile


class GetContentResponse(ServerResponse):
    data: Union[GetFolderContentData, GetFileContentData]


UpdateContentOption = Literal["name", "description", "tags", "public", "expiry", "password"]


"""
For attribute "name" : The name of the content (file or folder)
For attribute "description" : The description displayed on the download page (folder only)
For attribute "tags" : A comma-separated list of tags (folder only)
For attribute "public" : either "true" or "false (folder only)
For attribute "expiry" : A unix timestamp of the expiration date (folder only)
For attribute "password" : The password to set (folder only)
"""
UpdateContentOptionValue = Union[str, int]


class UploadFileData(TypedDict):
    # guestToken: str
    downloadPage: str
    code: str
    parentFolder: str
    fileId: str
    fileName: str
    md5: str


class UploadFileResponse(ServerResponse):
    data: UploadFileData


class UpdateContentResponse(ServerResponse):
    # AFAICT This is always empty
    data: dict


class DeleteContentsResponse(ServerResponse):
    data: dict[str, UpdateContentResponse]


class CompletedFileUploadResult(UploadFileData):
    filePath: str
    filePathMD5: str
    fileNameMD5: str
    uploadSuccess: Optional[str]


class GofileCLIArgs(TypedDict):
    file: str
    token: Optional[str]
    folder: Optional[str]
    connections: int
    public: bool
    no_save: bool


class GofileCLIDebugOptions(TypedDict):
    save_js_locally: Optional[bool]
    create_config: Optional[bool]


class GofileUploaderLocalConfigHistory(TypedDict):
    uploads: list[dict]
    md5_sums: dict[str, str]


class GofileUploaderLocalConfigOptions(TypedDict):
    token: Optional[str]
    zone: Optional[str]
    connections: Optional[int]
    public: Optional[bool]
    save: Optional[bool]
    retries: Optional[int]
    history: GofileUploaderLocalConfigHistory


class GofileUploaderOptions(GofileUploaderLocalConfigOptions):
    dry_run: Optional[str]
    debug_save_js_locally: Optional[bool]
    rename_existing: Optional[bool]
    use_config: Optional[bool]
    folder: Optional[str]
    file: Path
    log_level: Literal["debug", "info", "warning", "error", "critical"]
    log_file: Optional[Path]
    timeout: int
    # These options are derived on runtime
    config_file_path: Optional[Path]
    config_directory: Optional[Path]

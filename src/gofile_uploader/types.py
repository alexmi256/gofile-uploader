from typing import Literal, Optional, TypedDict, Union


class ServerResponse(TypedDict):
    status: str


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
    id: str
    type: str
    name: str
    createTime: int
    size: int
    downloadCount: int
    md5: str
    mimetype: str
    serverSelected: str
    link: str
    thumbnail: str


class GetContentChildFolder(TypedDict):
    id: str
    type: str
    name: str
    code: str
    createTime: int
    public: bool
    childrenIds: list[str]


class GetContentData(TypedDict):
    isOwner: bool
    id: str
    type: str
    name: str
    parentFolder: str
    code: str
    createTime: int
    isRoot: bool
    public: bool
    totalDownloadCount: int
    totalSize: int
    childrenIds: list[str]
    children: dict[str, GetContentChildFile | GetContentChildFolder]


class GetContentResponse(ServerResponse):
    data: GetContentData


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

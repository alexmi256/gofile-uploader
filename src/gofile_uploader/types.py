from typing import Literal, TypedDict, Union


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


class GetContentIndividualContent(TypedDict):
    id: str
    type: str
    name: str
    code: str
    # parentFolder: str
    createTime: int
    public: bool
    childrenIds: list[str]
    size: int
    downloadCount: int
    md5: str
    mimetype: str
    serverSelected: str
    # directLink: str
    link: str
    thumbnail: str


class GetContentData(TypedDict):
    # isOwner: bool
    id: str
    type: str
    name: str
    parentFolder: str
    code: str
    createTime: int
    public: bool
    childs: list[str]
    totalDownloadCount: int
    totalSize: int
    childrenIds: list[str]
    children: dict[str, GetContentIndividualContent]


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


class GofileCLIArgs(TypedDict):
    file: str
    token: Union[str, None]
    folder: Union[str, None]
    connections: int
    public: bool
    no_save: bool

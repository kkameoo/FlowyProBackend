from pydantic import BaseModel


class DeleteResponse(BaseModel):
    message: str


class DownloadLinkResponse(BaseModel):
    download_url: str
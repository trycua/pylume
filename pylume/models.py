from typing import Optional, List, Literal, Dict, Any
import re
from pydantic import BaseModel, Field, computed_field, validator, ConfigDict, RootModel

class DiskInfo(BaseModel):
    total: int
    allocated: int

class VMConfig(BaseModel):
    """Configuration for creating a new VM.
    
    Note: Memory and disk sizes should be specified with units (e.g., "4GB", "64GB")
    """
    name: str
    os: Literal["macOS", "linux"] = "macOS"
    cpu: int = Field(default=2, ge=1)
    memory: str = "4GB"
    disk_size: str = Field(default="64GB", alias="diskSize")
    display: str = "1024x768"
    ipsw: Optional[str] = Field(default=None, description="IPSW path or 'latest', for macOS VMs")

    class Config:
        populate_by_alias = True

class SharedDirectory(BaseModel):
    """Configuration for a shared directory."""
    host_path: str = Field(..., alias="hostPath")  # Allow host_path but serialize as hostPath
    read_only: bool = False
    
    class Config:
        populate_by_name = True  # Allow both alias and original name
        alias_generator = lambda s: ''.join(word.capitalize() if i else word for i, word in enumerate(s.split('_')))

class VMRunOpts(BaseModel):
    """Configuration for running a VM.
    
    Args:
        no_display: Whether to not display the VNC client
        shared_directories: List of directories to share with the VM
    """
    no_display: bool = Field(default=False, alias="noDisplay")
    shared_directories: Optional[list[SharedDirectory]] = Field(
        default=None, 
        alias="sharedDirectories"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=lambda s: ''.join(word.capitalize() if i else word for i, word in enumerate(s.split('_')))
    )

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Convert shared directory fields to match API expectations
        if self.shared_directories and "by_alias" in kwargs and kwargs["by_alias"]:
            data["sharedDirectories"] = [
                {
                    "hostPath": d.host_path,
                    "readOnly": d.read_only
                }
                for d in self.shared_directories
            ]
            # Remove the snake_case version if it exists
            data.pop("shared_directories", None)
        return data

class VMStatus(BaseModel):
    name: str
    status: str
    os: Literal["macOS", "linux"]
    cpu_count: int = Field(alias="cpuCount")
    memory_size: int = Field(alias="memorySize")  # API returns memory size in bytes
    disk_size: DiskInfo = Field(alias="diskSize")
    vnc_url: Optional[str] = Field(default=None, alias="vncUrl")
    ip_address: Optional[str] = Field(default=None, alias="ipAddress")

    class Config:
        populate_by_alias = True

    @computed_field
    @property
    def state(self) -> str:
        return self.status

    @computed_field
    @property
    def cpu(self) -> int:
        return self.cpu_count

    @computed_field
    @property
    def memory(self) -> str:
        # Convert bytes to GB
        gb = self.memory_size / (1024 * 1024 * 1024)
        return f"{int(gb)}GB"

class VMUpdateOpts(BaseModel):
    cpu: Optional[int] = None
    memory: Optional[str] = None
    disk_size: Optional[str] = None

class ImageRef(BaseModel):
    """Reference to a VM image."""
    image: str
    tag: str = "latest"
    registry: Optional[str] = "ghcr.io"
    organization: Optional[str] = "trycua"

    def model_dump(self, **kwargs):
        """Override model_dump to return just the image:tag format."""
        return f"{self.image}:{self.tag}"

class CloneSpec(BaseModel):
    """Specification for cloning a VM."""
    name: str
    new_name: str = Field(alias="newName")

    class Config:
        populate_by_alias = True

class ImageInfo(BaseModel):
    """Model for individual image information."""
    imageId: str

class ImageList(RootModel):
    """Response model for the images endpoint."""
    root: List[ImageInfo]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root) 
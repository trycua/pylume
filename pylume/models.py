from typing import Optional, List, Literal, Dict, Any
import re
from pydantic import BaseModel, Field, computed_field, validator, ConfigDict

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
    diskSize: str = "64GB"
    display: str = "1024x768"
    ipsw: Optional[str] = Field(default=None, description="IPSW path or 'latest', for macOS VMs")

    # No need for model_dump override since we want to send the sizes as strings

class SharedDirectory(BaseModel):
    host_path: str
    read_only: bool = False

class VMRunConfig(BaseModel):
    """Configuration for running a VM.
    
    Args:
        noDisplay: Whether to not display the VNC client
        sharedDirectories: List of directories to share with the VM
    """
    noDisplay: bool = False
    sharedDirectories: Optional[list[SharedDirectory]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "noDisplay": False,
                "sharedDirectories": [
                    {
                        "hostPath": "~/Projects",
                        "readOnly": False
                    }
                ]
            }
        }
        
    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Convert shared directory fields to match API expectations
        if self.sharedDirectories:
            data["sharedDirectories"] = [
                {
                    "hostPath": d.host_path,
                    "readOnly": d.read_only
                }
                for d in self.sharedDirectories
            ]
        return data

class VMStatus(BaseModel):
    name: str
    status: str
    os: Literal["macOS", "linux"]
    cpuCount: int
    memorySize: int  # API returns memory size in bytes
    diskSize: DiskInfo
    vncUrl: Optional[str] = None
    ipAddress: Optional[str] = None

    @computed_field
    @property
    def state(self) -> str:
        return self.status

    @computed_field
    @property
    def cpu(self) -> int:
        return self.cpuCount

    @computed_field
    @property
    def memory(self) -> str:
        # Convert bytes to GB
        gb = self.memorySize / (1024 * 1024 * 1024)
        return f"{int(gb)}GB"

    @computed_field
    @property
    def disk_size(self) -> str:
        # Convert bytes to GB
        gb = self.diskSize.total / (1024 * 1024 * 1024)
        return f"{int(gb)}GB"

class VMUpdateConfig(BaseModel):
    cpu: Optional[int] = None
    memory: Optional[str] = None
    disk_size: Optional[str] = None

class PullConfig(BaseModel):
    """Configuration for pulling a VM image.
    
    Example:
        PullConfig(
            image="macos-sequoia-vanilla",
            tag="15.2",
            name="my-vm"
        )
    """
    image: str  # Base image name without tag
    tag: str = "latest"  # Image tag
    name: Optional[str] = None  # Optional VM name
    registry: str = "ghcr.io"
    organization: str = "trycua"

    @computed_field
    @property
    def full_image(self) -> str:
        """Get the full image name with tag."""
        return f"{self.image}:{self.tag}"

class CloneConfig(BaseModel):
    name: str
    new_name: str

class ImageList(BaseModel):
    """Response model for the images endpoint."""
    local: List[str] = Field(description="List of local images available") 
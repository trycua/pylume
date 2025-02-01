import asyncio
from pylume import (
    PyLume, 
    ImageRef, 
    VMRunOpts, 
    SharedDirectory, 
    VMConfig,
    VMUpdateOpts
)

async def main():
    """Example usage of PyLume."""
    async with PyLume(debug=True) as pylume:

        # Create a new VM
        print("\n=== Creating a new VM ===")
        vm_config = VMConfig(
            name="lume-vm-new",
            os="macOS",
            cpu=2, 
            memory="4GB",
            disk_size="64GB",
            display="1024x768",
            ipsw="latest"
        )
        await pylume.create_vm(vm_config)

        # Get latest IPSW URL
        print("\n=== Getting Latest IPSW URL ===")
        url = await pylume.get_latest_ipsw_url()
        print("Latest IPSW URL:", url)

        # List available images
        print("\n=== Listing Available Images ===")
        images = await pylume.get_images()
        print("Available Images:", images)
        
        # List all VMs to verify creation
        print("\n=== Listing All VMs ===")
        vms = await pylume.list_vms()
        print("VMs:", vms)

        # Get specific VM details
        print("\n=== Getting VM Details ===")
        vm = await pylume.get_vm("lume-vm")
        print("VM Details:", vm)

        # Update VM settings
        print("\n=== Updating VM Settings ===")
        update_opts = VMUpdateOpts(
            cpu=8,
            memory="4GB"
        )
        await pylume.update_vm("lume-vm", update_opts)

        # Pull an image 
        image_ref = ImageRef(
            image="macos-sequoia-vanilla",
            tag="latest",
            registry="ghcr.io",
            organization="trycua"
        )
        await pylume.pull_image(image_ref, name="lume-vm-pulled")

        # Run with shared directory
        run_opts = VMRunOpts(
            no_display=False,
            shared_directories=[
                SharedDirectory(
                    host_path="/Users/<USER>/shared",
                    read_only=False
                )
            ]
        )
        await pylume.run_vm("lume-vm", run_opts)

        # Or simpler:
        await pylume.run_vm("lume-vm")

        # Clone VM
        print("\n=== Cloning VM ===")
        await pylume.clone_vm("lume-vm", "lume-vm-cloned")

        # Stop VM
        print("\n=== Stopping VM ===")
        await pylume.stop_vm("lume_vm")

        # Delete VM
        print("\n=== Deleting VM ===")
        await pylume.delete_vm("lume_vm_cloned")

if __name__ == '__main__':
    asyncio.run(main())

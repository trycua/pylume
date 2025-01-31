import asyncio

# Handle both package imports and direct module execution
try:
    from pylume.pylume import PyLume
    from pylume.models import PullConfig
except ImportError:
    # For direct module execution
    from pylume import PyLume
    from models import PullConfig

async def main():
    """Async playground for testing PyLume client."""
    async with PyLume(debug=True, port=3001) as pylume:
        # Get available images
        vms = await pylume.list_vms()
        print("VMs:", vms)
        
        # Example: Pull an image
        # config = PullConfig(
        #     image="macos-sequoia-vanilla",
        #     tag="15.2",
        #     name="test-vm"
        # )
        # await pylume.pull_image(config)
        
        # Example: List VMs
        # vms = await pylume.list_vms()
        # print("VMs:", vms)

if __name__ == '__main__':
    asyncio.run(main())

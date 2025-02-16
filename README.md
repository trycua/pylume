<div align="center">
<h1>
  <div class="image-wrapper" style="display: inline-block;">
    <picture>
      <source media="(prefers-color-scheme: dark)" alt="logo" height="150" srcset="img/logo_white.png" style="display: block; margin: auto;">
      <source media="(prefers-color-scheme: light)" alt="logo" height="150" srcset="img/logo_black.png" style="display: block; margin: auto;">
      <img alt="Shows my svg">
    </picture>
  </div>

  [![Python](https://img.shields.io/badge/Python-333333?logo=python&logoColor=white&labelColor=333333)](#)
  [![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=F0F0F0)](#)
  [![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white)](https://discord.com/invite/mVnXXpdE85)
  [![PyPI](https://img.shields.io/pypi/v/pylume?color=333333)](https://pypi.org/project/pylume/)
</h1>
</div>


**pylume** is a lightweight Python library based on [lume](https://github.com/trycua/lume) to create, run and manage macOS and Linux virtual machines (VMs) natively on Apple Silicon.

<div align="center">
<img src="img/py.png" alt="lume-py">
</div>


```bash
pip install pylume
```

## Usage

Please refer to this [Notebook](./samples/nb.ipynb) for a quickstart. More details about the underlying API used by pylume are available [here](https://github.com/trycua/lume/docs/API-Reference.md).

## Prebuilt Images

Pre-built images are available on [ghcr.io/trycua](https://github.com/orgs/trycua/packages). 
These images come pre-configured with an SSH server and auto-login enabled.

## Contributing

We welcome and greatly appreciate contributions to lume! Whether you're improving documentation, adding new features, fixing bugs, or adding new VM images, your efforts help make pylume better for everyone.

Join our [Discord community](https://discord.com/invite/mVnXXpdE85) to discuss ideas or get assistance.

## License

lume is open-sourced under the MIT License - see the [LICENSE](LICENSE) file for details.

## Stargazers over time

[![Stargazers over time](https://starchart.cc/trycua/pylume.svg?variant=adaptive)](https://starchart.cc/trycua/pylume)

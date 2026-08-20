# Python Environment Management

## Virtual Environment Setup
You CAN and SHOULD create Python virtual environments when working on Python projects:
- Create venv: `python -m venv venv` or `python3 -m venv venv`
- Activate venv:
  - Linux/macOS: `source venv/bin/activate`
  - Windows: `venv\Scripts\activate`
- Deactivate: `deactivate`

## Package Installation
You CAN install Python packages using pip within the activated virtual environment:
- Install single package: `pip install package_name`
- Install from requirements.txt: `pip install -r requirements.txt`
- Install with extras: `pip install package[extra]`
- Upgrade packages: `pip install --upgrade package_name`

## Important Notes
- Always create and activate a virtual environment before installing packages
- Use pip within the venv, NOT system-wide installation
- If `uv` is available in the project, prefer `uv venv` and `uv pip install` over regular pip
- You have full capability to execute these commands - don't hesitate to set up proper Python environments

## WSL on Windows-Mounted Drives (/mnt/)
If you encounter symlink errors on Windows-mounted drives in WSL (e.g., `/mnt/h/`, `/mnt/c/`):

### Option 1: Work in Linux filesystem (RECOMMENDED)
Move to the Linux filesystem where symlinks work properly:
```bash
cd ~  # or any directory NOT under /mnt/
git clone <your-repo>
cd <your-repo>
python -m venv venv  # This will work!
```

### Option 2: Enable metadata on the mount
Add to `/etc/wsl.conf` (create if doesn't exist):
```
[automount]
options = "metadata"
```
Then restart WSL: `wsl --shutdown` and reopen

### Option 3: Use virtualenv instead of venv
```bash
pip install virtualenv
virtualenv venv --copies
```

### Option 4: Create venv in WSL filesystem, symlink to project
```bash
# Create venv in home directory
python -m venv ~/venvs/project-name
# Create symlink in your project (this type of symlink usually works)
ln -s ~/venvs/project-name venv
# Activate as normal
source venv/bin/activate
```

Remember: The issue is that Windows filesystems mounted in WSL don't support Linux-style symlinks. The Python venv module tries to create a `lib64 -> lib` symlink even with `--copies` flag.

## Common Python Commands
- `pip freeze > requirements.txt`: Save current dependencies
- `pip list`: Show installed packages
- `which python` or `where python`: Verify you're using venv Python
- `python -m pytest`: Run tests
- `python -m black .`: Format code
- `python -m mypy .`: Type check
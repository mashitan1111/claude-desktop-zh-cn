$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$setup = Join-Path $root "scripts\setup_claude_zh_proxy.py"

python -m pip install -r (Join-Path $root "requirements.txt")
python $setup --install --start --clear-cache

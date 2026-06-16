$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$setup = Join-Path $root "scripts\setup_claude_zh_proxy.py"

python $setup --uninstall

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if os.name == "nt":
    import ctypes
    import winreg

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


HOST = "assets-proxy.anthropic.com"
PROXY_HOSTS = [
    "assets-proxy.anthropic.com",
    "a-cdn.claude.ai",
]
OLD_MANAGED_HOSTS = {
    "a.claude.ai",
}
MARKER = "# Codex Claude zh proxy"

ROOT = Path(__file__).resolve().parent
WORK_DIR = ROOT.parent
PROJECT_ROOT = WORK_DIR if ROOT.name.lower() == "scripts" else ROOT
OUTPUTS = PROJECT_ROOT / "outputs"
CERT_DIR = ROOT / "certs"
ROOT_KEY = CERT_DIR / "root_ca_key.pem"
ROOT_CERT = CERT_DIR / "root_ca.crt"
HOST_KEY = CERT_DIR / "assets_proxy_key.pem"
HOST_CERT = CERT_DIR / "assets_proxy_cert.pem"
UPSTREAM_IP_FILE = ROOT / "upstream_ip.txt"
UPSTREAM_IPS_FILE = ROOT / "upstream_ips.json"
HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")
PROXY_SCRIPT = ROOT / "claude_zh_proxy.py"
LOG_FILE = ROOT / "proxy-start.log"
PID_FILE = ROOT / "proxy.pid"
CLAUDE_EXE = Path(r"C:\Program Files\WindowsApps\Claude_1.12603.1.0_x64__pzs8sxrjxfjjc\app\Claude.exe")
NATIVE_LOCALE_FIXES = {
    "Y217GbcTlO": "\u67e5\u627e\u4e0b\u4e00\u4e2a",
    "tjZvRtHnCc": "\u67e5\u627e\u4e0a\u4e00\u4e2a",
    "r6AwevAvuz": "\u91ca\u653e Cowork \u78c1\u76d8\u7a7a\u95f4\u2026",
}
NATIVE_LOCALE_FILES = ("en-US.json", "zh-CN.json")


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def powershell(script: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=check)


def certificate_covers_hosts() -> bool:
    if not HOST_CERT.exists():
        return False
    try:
        cert = x509.load_pem_x509_certificate(HOST_CERT.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = {name.lower() for name in san.get_values_for_type(x509.DNSName)}
        return all(host.lower() in names for host in PROXY_HOSTS)
    except Exception:
        return False


def generate_certificates() -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if ROOT_CERT.exists() and ROOT_KEY.exists() and HOST_CERT.exists() and HOST_KEY.exists() and certificate_covers_hosts():
        return

    now = dt.datetime.now(dt.timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Codex Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Codex Claude Zh Proxy Root CA"),
        ]
    )
    root_cert = (
        x509.CertificateBuilder()
        .subject_name(root_subject)
        .issuer_name(root_subject)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(True, False, True, False, False, True, False, False, False), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    host_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Codex Local"),
            x509.NameAttribute(NameOID.COMMON_NAME, HOST),
        ]
    )
    host_cert = (
        x509.CertificateBuilder()
        .subject_name(host_subject)
        .issuer_name(root_subject)
        .public_key(host_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(host) for host in PROXY_HOSTS]
                + [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(root_key, hashes.SHA256())
    )

    ROOT_KEY.write_bytes(
        root_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    ROOT_CERT.write_bytes(root_cert.public_bytes(serialization.Encoding.PEM))
    HOST_KEY.write_bytes(
        host_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    HOST_CERT.write_bytes(host_cert.public_bytes(serialization.Encoding.PEM))


def trust_root_certificate() -> None:
    result = run(["certutil", "-user", "-addstore", "Root", str(ROOT_CERT)], check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())


def resolve_host_upstream_ip(host: str) -> str:
    command = (
        f"Resolve-DnsName {host} -Server 1.1.1.1 -Type A | "
        "Where-Object {$_.IPAddress -and $_.IPAddress -ne '127.0.0.1'} | "
        "Select-Object -First 1 -ExpandProperty IPAddress"
    )
    result = powershell(command, check=False)
    ip = (result.stdout or "").strip().splitlines()[0].strip() if result.stdout.strip() else ""
    if not ip:
        ip = socket.gethostbyname(host)
    if ip == "127.0.0.1":
        raise RuntimeError(f"upstream DNS resolved to localhost for {host}")
    return ip


def resolve_upstream_ip() -> str:
    ips = {host: resolve_host_upstream_ip(host) for host in PROXY_HOSTS}
    UPSTREAM_IPS_FILE.write_text(json.dumps(ips, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ip = ips[HOST]
    UPSTREAM_IP_FILE.write_text(ip, encoding="ascii")
    return ip


def ensure_hosts() -> None:
    text = HOSTS.read_text(encoding="ascii", errors="ignore")
    backup = ROOT / ("hosts.backup." + dt.datetime.now().strftime("%Y%m%d%H%M%S"))
    if MARKER not in text:
        backup.write_text(text, encoding="ascii")
    proxy_hosts = {host.lower() for host in PROXY_HOSTS}
    lines = []
    for line in text.splitlines():
        if MARKER in line:
            continue
        parts = line.split("#", 1)[0].split()
        if len(parts) >= 2 and proxy_hosts.intersection(part.lower() for part in parts[1:]):
            continue
        lines.append(line.rstrip())
    lines.append(f"127.0.0.1 {' '.join(PROXY_HOSTS)} {MARKER}")
    HOSTS.write_text("\n".join(lines).rstrip() + "\n", encoding="ascii")


def remove_hosts() -> None:
    if not HOSTS.exists():
        return
    text = HOSTS.read_text(encoding="ascii", errors="ignore")
    lines = [line.rstrip() for line in text.splitlines() if MARKER not in line]
    HOSTS.write_text("\n".join(lines).rstrip() + "\n", encoding="ascii")


def is_port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 443), timeout=1):
            return True
    except OSError:
        return False


def health_ok() -> bool:
    try:
        context = ssl._create_unverified_context()
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context),
        )
        with opener.open(f"https://{HOST}/claude-zh-cn/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def refresh_internet_settings() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.wininet.InternetSetOptionW(0, 37, 0, 0)
    except Exception:
        pass


def ensure_proxy_override() -> bool:
    if os.name != "nt":
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "ProxyOverride")
        except FileNotFoundError:
            current = ""
        parts = [part.strip() for part in str(current).split(";") if part.strip()]
        wanted = {host.lower() for host in PROXY_HOSTS}
        new_parts = [part for part in parts if part.lower() not in OLD_MANAGED_HOSTS]
        existing = {part.lower() for part in new_parts}
        if wanted.issubset(existing) and new_parts == parts:
            return False
        backup = ROOT / ("ProxyOverride.backup." + dt.datetime.now().strftime("%Y%m%d%H%M%S") + ".txt")
        backup.write_text(str(current), encoding="utf-8")
        for host in PROXY_HOSTS:
            if host.lower() not in existing:
                new_parts.append(host)
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, ";".join(new_parts))
    refresh_internet_settings()
    return True


def remove_proxy_override() -> bool:
    if os.name != "nt":
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    managed = {host.lower() for host in PROXY_HOSTS} | OLD_MANAGED_HOSTS
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            current, _ = winreg.QueryValueEx(key, "ProxyOverride")
        except FileNotFoundError:
            return False
        parts = [part.strip() for part in str(current).split(";") if part.strip()]
        new_parts = [part for part in parts if part.lower() not in managed]
        if new_parts == parts:
            return False
        backup = ROOT / ("ProxyOverride.backup." + dt.datetime.now().strftime("%Y%m%d%H%M%S") + ".txt")
        backup.write_text(str(current), encoding="utf-8")
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, ";".join(new_parts))
    refresh_internet_settings()
    return True


def is_pid_running(pid: int) -> bool:
    result = powershell(f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id", check=False)
    return result.returncode == 0 and str(pid) in (result.stdout or "")


def stop_proxy() -> bool:
    stopped = False
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="ascii").strip())
            if is_pid_running(pid):
                powershell(f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue", check=False)
                stopped = True
        except Exception:
            pass
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    return stopped


def start_proxy() -> None:
    if health_ok():
        return
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="ascii").strip())
            if is_pid_running(pid) and is_port_open():
                return
        except Exception:
            pass
    if is_port_open():
        raise RuntimeError("127.0.0.1:443 is already in use, but Claude zh proxy health check failed")

    log = LOG_FILE.open("ab")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    process = subprocess.Popen(
        [sys.executable, str(PROXY_SCRIPT)],
        cwd=str(ROOT),
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )
    PID_FILE.write_text(str(process.pid), encoding="ascii")
    for _ in range(30):
        if health_ok():
            return
        time.sleep(0.3)
    raise RuntimeError("Claude zh proxy did not become healthy")


def stop_claude() -> None:
    run(["taskkill", "/IM", "Claude.exe", "/F"], check=False)


def clear_claude_cache() -> list[str]:
    appdata = Path(os.environ.get("APPDATA", "")) / "Claude"
    removed: list[str] = []
    for name in ["Cache", "Code Cache", "GPUCache", "Service Worker", "Shared Dictionary"]:
        target = appdata / name
        try:
            if target.exists():
                shutil.rmtree(target)
                removed.append(str(target))
        except Exception:
            pass
    return removed


def patch_native_locale_files() -> list[str]:
    resources_dir = CLAUDE_EXE.parent / "resources"
    if not resources_dir.exists():
        return []

    backup_dir = resources_dir / ".zh-cn-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    changed: list[str] = []
    for name in NATIVE_LOCALE_FILES:
        path = resources_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        changed_keys: list[str] = []
        for key, value in NATIVE_LOCALE_FIXES.items():
            if data.get(key) != value:
                data[key] = value
                changed_keys.append(key)
        if not changed_keys:
            continue

        shutil.copy2(path, backup_dir / f"{name}.before-native-locale-{timestamp}.json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(f"{name}:{','.join(changed_keys)}")
    return changed


def launcher_paths() -> tuple[Path, Path]:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    return OUTPUTS / "claude-zh-launcher.ps1", OUTPUTS / "claude-zh-launcher.vbs"


def write_launchers() -> tuple[Path, Path]:
    ps1, vbs = launcher_paths()
    ps1.write_text(
        f"""$ErrorActionPreference = 'SilentlyContinue'
$setup = {json.dumps(str(ROOT / "setup_claude_zh_proxy.py"), ensure_ascii=False)}
$claude = {json.dumps(str(CLAUDE_EXE), ensure_ascii=False)}
python $setup --install --start | Out-Null
Start-Sleep -Milliseconds 700
Start-Process -FilePath $claude
""",
        encoding="utf-8-sig",
    )
    vbs.write_text(
        'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""{ps1}""", 0, False\n',
        encoding="utf-8",
    )
    return ps1, vbs


def desktop_shortcut_path() -> Path:
    desktop_result = powershell("[Environment]::GetFolderPath('Desktop')", check=True)
    return Path(desktop_result.stdout.strip()) / "Claude 中文版.lnk"


def create_shortcut() -> Path:
    _, vbs = write_launchers()
    shortcut = desktop_shortcut_path()
    icon = str(CLAUDE_EXE).replace("'", "''")
    target = str(vbs).replace("'", "''")
    shortcut_target = str(shortcut).replace("'", "''")
    working_directory = str(OUTPUTS).replace("'", "''")
    script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{shortcut_target}')
$shortcut.TargetPath = 'wscript.exe'
$shortcut.Arguments = '"{target}"'
$shortcut.IconLocation = '{icon},0'
$shortcut.WorkingDirectory = '{working_directory}'
$shortcut.WindowStyle = 7
$shortcut.Save()
"""
    powershell(script, check=True)
    return shortcut


def install(start: bool = False, clear_cache: bool = False) -> dict:
    generate_certificates()
    trust_root_certificate()
    upstream_ip = resolve_upstream_ip()
    ensure_hosts()
    native_locale_changes = patch_native_locale_files()
    proxy_override_changed = ensure_proxy_override()
    shortcut = create_shortcut()
    removed = []
    if clear_cache:
        stop_claude()
        time.sleep(0.5)
        removed = clear_claude_cache()
    if start:
        start_proxy()
    return {
        "status": "installed",
        "upstream_ip": upstream_ip,
        "shortcut": str(shortcut),
        "proxy_override_changed": proxy_override_changed,
        "native_locale_changes": native_locale_changes,
        "cache_removed": removed,
        "health": health_ok(),
    }


def uninstall() -> dict:
    stopped = stop_proxy()
    remove_hosts()
    proxy_override_changed = remove_proxy_override()
    shortcut_removed = False
    try:
        shortcut = desktop_shortcut_path()
        if shortcut.exists():
            shortcut.unlink()
            shortcut_removed = True
    except Exception:
        pass
    return {
        "status": "uninstalled",
        "proxy_stopped": stopped,
        "hosts_removed": True,
        "proxy_override_changed": proxy_override_changed,
        "shortcut_removed": shortcut_removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    if args.uninstall:
        result = uninstall()
    elif args.install:
        result = install(start=args.start, clear_cache=args.clear_cache)
    elif args.start:
        native_locale_changes = patch_native_locale_files()
        start_proxy()
        result = {"status": "started", "native_locale_changes": native_locale_changes, "health": health_ok()}
    else:
        parser.error("Use --install, --start, or --uninstall")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

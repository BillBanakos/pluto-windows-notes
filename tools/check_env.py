#!/usr/bin/env python3
"""
check_env.py - one-shot health check for a PlutoSDR / Pluto+ Python setup on Windows.

Checks, in order, and stops explaining at the first real problem:
  1. Python / pip / venv
  2. libiio C library (libiio.dll) present
  3. `import iio` works (catches the find_library("c") crash)
  4. pylibiio (Python bindings) version vs libiio C library version
  5. `import adi` (pyadi-iio)
  6. the stray libxml.dll that prints "program compiled against libxml 2 using libxml 20"
  7. connect to the radio and list its devices

    python tools/check_env.py
    python tools/check_env.py --uri usb:1.5.5      # or ip:pluto.local
"""
import argparse
import os
import platform
import sys
from importlib import metadata

OK, WARN, FAIL = "[ OK ]", "[WARN]", "[FAIL]"


def pkg_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uri", default="ip:192.168.2.1", help="radio URI (default ip:192.168.2.1)")
    a = p.parse_args()

    print(f"Python {platform.python_version()} ({sys.executable}) on {platform.platform()}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"{OK if in_venv else WARN} venv active: {in_venv}"
          + ("" if in_venv else "  -> python -m venv .venv ; .\\.venv\\Scripts\\Activate.ps1"))
    pip_v = pkg_version("pip")
    print(f"{OK if pip_v else FAIL} pip {pip_v or 'missing  -> python -m ensurepip --upgrade'}")

    # 2. C library
    if os.name == "nt":
        dll = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "libiio.dll")
        have = os.path.exists(dll)
        print(f"{OK if have else FAIL} {dll} exists: {have}"
              + ("" if have else "  -> install libiio from github.com/analogdevicesinc/libiio/releases"))
        libxml = os.path.join(os.path.dirname(dll), "libxml.dll")
        if os.path.exists(libxml):
            print(f"{WARN} {libxml} found - likely source of 'compiled against libxml 2 using libxml 20' (harmless)")

    # 3. bindings
    try:
        import iio
    except TypeError as e:
        print(f"{FAIL} import iio -> TypeError: {e}")
        print("       find_library('c') returned None. See README: 'import adi -> TypeError NoneType'.")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} import iio -> {type(e).__name__}: {e}")
        return 1

    py_v = pkg_version("pylibiio")
    c_v = getattr(iio, "version", None)  # (major, minor, git-tag) of the loaded C library
    c_str = f"{c_v[0]}.{c_v[1]}" if c_v else "unknown"
    print(f"{OK} import iio   pylibiio {py_v or '?'}   libiio C library {c_str}"
          + (f" ({c_v[2]})" if c_v and len(c_v) > 2 else ""))
    if py_v and c_v:
        if py_v.split(".")[0] != str(c_v[0]):
            print(f"{FAIL} major version mismatch: bindings {py_v} vs C library {c_str}")
            print(f"       -> pip install pylibiio=={c_v[0]}.{c_v[1]}   (e.g. 0.25 for libiio 0.25)")
        elif ".".join(py_v.split(".")[:2]) != c_str:
            print(f"{WARN} minor version differs: bindings {py_v} vs C library {c_str}")

    # 5. pyadi-iio
    try:
        import adi  # noqa: F401
        print(f"{OK} import adi   pyadi-iio {pkg_version('pyadi-iio') or '?'}")
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} import adi -> {type(e).__name__}: {e}   -> pip install pyadi-iio")

    # 7. radio
    try:
        ctx = iio.Context(a.uri)
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} connect {a.uri} -> {type(e).__name__}: {e}")
        print("       try:  iio_info -s   (scan)   and   ping 192.168.2.1")
        return 1
    print(f"{OK} connected to {a.uri}: {getattr(ctx, 'name', '?')} / {getattr(ctx, 'description', '')}")
    attrs = getattr(ctx, "attrs", {}) or {}
    for k in ("hw_model", "fw_version", "hw_serial"):
        if k in attrs:
            print(f"       {k:10s} {attrs[k]}")
    devs = [d.name for d in ctx.devices]
    print(f"       devices: {', '.join(n for n in devs if n)}")
    if not any(n and "ad9361-phy" in n for n in devs):
        print(f"{WARN} no ad9361-phy device - is this a Pluto?")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# PlutoSDR / Pluto+ on Windows: troubleshooting notes

These are field notes from getting an **ADALM-Pluto / Pluto+ (AD9361)** working with
**Python (pyadi-iio + libiio) on Windows**. Each problem below came up on real hardware
while building [rf-graffiti](https://github.com/BillBanakos/rf-graffiti) and a 2-channel
angle-of-arrival demo. Error messages are copied exactly, so you can find them with your
browser's search.

There are also three small scripts that find the problems for you:

| Script | What it tells you |
|---|---|
| `tools/check_env.py` | venv, pip, libiio DLL, binding/library version mismatch, `import adi`, connection to the radio |
| `tools/tone_test.py` | whether TX1 actually reaches RX1 (single-tone loopback) |
| `tools/loop_test.py` | how much of a cyclic TX buffer the radio really plays |

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\check_env.py
```

Loopback tests need **TX1 → 30 dB attenuator → RX1**. Never cable TX straight into RX.

---

## Quick index

| You see | Jump to |
|---|---|
| `running scripts is disabled on this system` | [1](#1-powershell-blocks-activateps1) |
| `No module named pip` / pip missing on a new Python | [2](#2-pip-missing) |
| `TypeError: argument of type 'NoneType' is not iterable` on `import adi` | [3](#3-import-adi--typeerror-nonetype-is-not-iterable) |
| `Fatal: program compiled against libxml 2 using libxml 20` | [4](#4-fatal-program-compiled-against-libxml-2-using-libxml-20) |
| `OSError: [Errno 0] No error` when creating `adi.Pluto` / `adi.ad9361`, but `iio_info` works | [5](#5-oserror-errno-0-no-error-binding-version-mismatch) |
| Tones look fine, but images/text or anything that starts with silence never appears | [6](#6-only-25--of-a-cyclic-tx-buffer-is-played) |
| `OSError: Open unlocked: -27` on `tx()` | [7](#7-oserror-open-unlocked--27-on-tx) |
| A second `tx()` call doesn't change what's transmitted | [8](#8-a-second-tx-doesnt-update-the-output) |
| A spike in the middle of every spectrum | [9](#9-the-spike-at-the-centre) |

---

### 1. PowerShell blocks `Activate.ps1`

```
.\.venv\Scripts\Activate.ps1 : File ... cannot be loaded because running scripts is disabled on this system.
```

Run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Or skip activation and call the venv's Python directly: `.\.venv\Scripts\python.exe script.py`.

### 2. pip missing

On a new Python install, pip is sometimes missing. Bootstrap it with `python -m ensurepip --upgrade`,
or create a venv (`python -m venv .venv`), which installs pip into the venv. Then install the
packages inside the venv.
Brand-new Python releases can lag behind on wheels for compiled packages. If `pip install` starts
compiling numpy or scipy from source, use the previous Python minor version instead.

### 3. `import adi` → TypeError: NoneType is not iterable

```
File "...\site-packages\iio\__init__.py", line ..., in <module>
TypeError: argument of type 'NoneType' is not iterable
```

**Cause:** the bindings call `ctypes.util.find_library("c")`, which returns `None` on Windows with
recent Python versions. The `None` then crashes the next line.

**Fix:** patch that call to load the Microsoft C runtime instead (venv active, from the project folder):

```powershell
(Get-Content .venv\Lib\site-packages\iio\__init__.py) -replace 'find_library\("c"\)', '"msvcrt"' |
    Set-Content .venv\Lib\site-packages\iio\__init__.py
```

You have to redo the patch every time `pylibiio` is reinstalled.

### 4. `Fatal: program compiled against libxml 2 using libxml 20`

The message appears once or twice when the radio connects, and **it is harmless**: the script keeps
running. It comes from a libxml DLL version clash. If you want it gone, check whether
`C:\Windows\System32\libxml.dll` exists (as opposed to `libxml2.dll`). If it does, rename it,
e.g. to `libxml.dll.bak`. `check_env.py` reports it if present.

### 5. `OSError: [Errno 0] No error` (binding version mismatch)

The symptoms: `iio_info -u ip:192.168.2.1` works, `import adi` works, but creating the device fails
with a cryptic `OSError`.

**Cause:** pip installs the newest `pylibiio` (1.x bindings), but the Windows installer put the
**0.2x** C library in System32. The two must match:

```powershell
pip install pylibiio==0.25     # for libiio 0.25 installed system-wide
```

`check_env.py` prints both versions and flags a mismatch. `where.exe iio_info` should resolve to
`C:\Windows\System32\iio_info.exe`. If it does, the C library is on the PATH and nothing else
needs changing.

### 6. Only 25 % of a cyclic TX buffer is played

The symptoms: a single tone or noise transmits fine, but a structured signal (an image painted into
the waterfall, a frame that starts with silence) shows nothing or only fragments.

**Diagnose** with `tools/loop_test.py`. It sends a staircase of tones and reports which part of
the buffer comes out:

```
N=200000:  freqs seen -427 .. -229 kHz -> ~49,002 of 200,000 samples actually loop
N=2000000: freqs seen -450 .. -226 kHz -> ~497,884 of 2,000,000 samples actually loop
```

(real output from a Pluto+). Exactly a quarter plays, independent of the buffer size. A continuous
tone still looks right because any quarter of it is still a tone.

**Workaround:** transmit the buffer tiled 4×. The quarter that plays is then one full copy, and
nothing breaks if the bug ever goes away:

```python
sdr.tx(np.tile(iq, 4) * 2**14)
```

**Likely cause (not confirmed):** the factor of exactly 4 matches the 4 bytes per complex
16-bit sample, so somewhere a length is probably counted in bytes instead of samples. A
bindings/library version mismatch (see [5](#5-oserror-errno-0-no-error-binding-version-mismatch))
is the prime suspect. After fixing the versions, re-run `loop_test.py`. If it reports ~100 %,
stop tiling.

### 7. `OSError: Open unlocked: -27` on `tx()`

`-27` is `EFBIG`: the TX buffer is too large for the kernel to allocate. Common causes are a high
sample rate × a long duration, or the 4× tiling from [6](#6-only-25--of-a-cyclic-tx-buffer-is-played)
pushing a buffer past the limit. Reduce `fs × duration × tiling`: shorten the loop, lower the sample
rate, or tile less. A few million complex samples worked on the Pluto+ used for these notes; the
exact limit depends on firmware and memory.

### 8. A second `tx()` doesn't update the output

With `tx_cyclic_buffer = True`, the first buffer keeps looping. Call `sdr.tx_destroy_buffer()`
before sending a new one. If the output still doesn't change, delete the `adi.Pluto` object and
reconnect (that takes about 1 s). The test scripts run each measurement in a fresh process
for this reason.

### 9. The spike at the centre

The line at 0 Hz offset is DC offset and TX LO leakage, and it is normal. Put your signals at an
offset from the LO (the test scripts use +200 kHz) and ignore the few bins around DC when you
look for peaks.

---

## Known-good setup

| Component | Version used |
|---|---|
| Windows | x64 |
| libiio (system, from the ADI Windows installer) | 0.25 |
| pylibiio | 0.25 (pinned) |
| pyadi-iio | latest from pip |
| Radio | Pluto+ (AD9361, 2R2T) at `ip:192.168.2.1` |

## Contributing

Ran into something else? Open an issue with the exact error text, the output of
`python tools\check_env.py`, and what fixed it.

## License

[MIT](LICENSE) © 2026 Vasileios Banakos

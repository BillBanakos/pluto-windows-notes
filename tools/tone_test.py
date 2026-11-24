#!/usr/bin/env python3
"""
tone_test.py - loopback sanity check: does TX1 reach RX1?

Transmits one CW tone from a cyclic buffer and reports where RX1 sees the peak.

Setup: Pluto TX1 --[30 dB attenuator]--> Pluto RX1   (never connect TX to RX directly)

    python tools/tone_test.py
    python tools/tone_test.py --freq 400e3 --n 2000000

Expected: peak at the tone offset, tens of dB above the floor -> OK.
Run each test in a fresh process: a second tx() on the same connection may not update.
"""
import argparse

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uri", default="ip:192.168.2.1")
    p.add_argument("--lo", type=float, default=1e9, help="LO frequency [Hz]")
    p.add_argument("--fs", type=float, default=1e6, help="sample rate [Hz]")
    p.add_argument("--freq", type=float, default=200e3, help="tone offset from LO [Hz]")
    p.add_argument("--n", type=int, default=500_000, help="TX buffer length [samples]")
    p.add_argument("--tx-gain", type=float, default=-20, help="TX attenuation [dB, <= 0]")
    p.add_argument("--rx-gain", type=float, default=20, help="RX manual gain [dB]")
    a = p.parse_args()

    import adi
    s = adi.Pluto(a.uri)
    s.sample_rate = int(a.fs)
    s.tx_lo = s.rx_lo = int(a.lo)
    s.tx_hardwaregain_chan0 = a.tx_gain
    s.gain_control_mode_chan0 = "manual"
    s.rx_hardwaregain_chan0 = a.rx_gain
    s.rx_buffer_size = 4096
    s.tx_cyclic_buffer = True

    n = np.arange(a.n)
    s.tx((0.5 * 2**14 * np.exp(2j * np.pi * a.freq * n / a.fs)).astype(np.complex64))
    for _ in range(5):  # flush stale buffers
        s.rx()
    x = s.rx()
    s.tx_destroy_buffer()

    spec = 20 * np.log10(np.abs(np.fft.fftshift(np.fft.fft(x))) + 1)
    c = len(x) // 2
    spec[c - 3:c + 4] = 0  # ignore DC / LO leakage
    k = int(np.argmax(spec))
    peak = (k - c) * a.fs / len(x)
    ok = abs(peak - a.freq) < 2 * a.fs / len(x) + 1e3
    print(f"N={a.n:>8}  tone {a.freq/1e3:7.1f} kHz -> peak {peak/1e3:7.1f} kHz, "
          f"{spec[k] - np.median(spec):5.1f} dB above floor  ->  {'OK' if ok else 'FAIL'}")
    if not ok:
        print("Check: cable on TX1/RX1 (not TX2/RX2), attenuator, LO within range, gains.")


if __name__ == "__main__":
    main()

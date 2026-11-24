#!/usr/bin/env python3
"""
loop_test.py - measure how much of a cyclic TX buffer the Pluto actually plays.

The TX buffer is a staircase of tones that rises from -0.45*fs to +0.45*fs
along the buffer, so a tone's frequency tells you its position in the buffer.
RX listens for longer than one loop and records which steps appear. If the
highest step seen is a quarter of the way up, only a quarter of the buffer is
being looped.

Setup: Pluto TX1 --[30 dB attenuator]--> Pluto RX1

    python tools/loop_test.py --n 200000
    python tools/loop_test.py --n 2000000

  ~100 %  -> the cyclic buffer works.
  ~25 %   -> only the first quarter plays: tile your buffer 4x (see README).
"""
import argparse
import time

import numpy as np


def staircase(n, fs, steps):
    seg = n // steps
    freqs = np.linspace(-0.45 * fs, 0.45 * fs, steps)
    ph = np.concatenate([2 * np.pi * f * np.arange(seg) / fs for f in freqs])
    x = np.exp(1j * ph)
    return np.pad(x, (0, n - len(x))), freqs


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uri", default="ip:192.168.2.1")
    p.add_argument("--lo", type=float, default=1e9)
    p.add_argument("--fs", type=float, default=1e6)
    p.add_argument("--n", type=int, default=2_000_000, help="TX buffer length [samples]")
    p.add_argument("--steps", type=int, default=64, help="number of tone steps along the buffer")
    p.add_argument("--tx-gain", type=float, default=-20)
    p.add_argument("--rx-gain", type=float, default=20)
    p.add_argument("--min-snr", type=float, default=20, help="dB above floor to count a step as seen")
    a = p.parse_args()

    import adi
    x, freqs = staircase(a.n, a.fs, a.steps)
    s = adi.Pluto(a.uri)
    s.sample_rate = int(a.fs)
    s.tx_lo = s.rx_lo = int(a.lo)
    s.tx_hardwaregain_chan0 = a.tx_gain
    s.gain_control_mode_chan0 = "manual"
    s.rx_hardwaregain_chan0 = a.rx_gain
    s.rx_buffer_size = 4096
    s.tx_cyclic_buffer = True
    s.tx((0.5 * 2**14 * x).astype(np.complex64))
    for _ in range(5):
        s.rx()

    loop_s = a.n / a.fs
    seen = np.zeros(a.steps, bool)
    t_end = time.time() + 1.5 * loop_s + 0.5
    while time.time() < t_end:
        y = s.rx()
        spec = np.abs(np.fft.fftshift(np.fft.fft(y * np.hanning(len(y)))))
        db = 20 * np.log10(spec + 1e-9)
        f = (np.arange(len(y)) - len(y) // 2) * a.fs / len(y)
        floor = np.median(db)
        for i, fi in enumerate(freqs):
            if abs(fi) < 5 * a.fs / len(y):  # skip the step sitting on DC / LO leakage
                continue
            if db[np.abs(f - fi) < 2 * a.fs / len(y)].max() - floor > a.min_snr:
                seen[i] = True
    s.tx_destroy_buffer()

    if not seen.any():
        print("no steps detected - run tone_test.py first")
        return
    last = int(np.nonzero(seen)[0].max())
    frac = (last + 1) / a.steps
    print(f"N={a.n}: freqs seen {freqs[seen].min()/1e3:.0f} .. {freqs[last]/1e3:.0f} kHz "
          f"-> ~{frac*a.n:,.0f} of {a.n:,} samples actually loop ({frac*100:.0f} %)")


if __name__ == "__main__":
    main()

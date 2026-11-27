#!/usr/bin/env python3
"""Round 61: music proven by SOUND. Compares WAV recordings made with boot-server's `audio start|save|stop`
(docs/harness/SERVER.md) by a simple spectral fingerprint (numpy only, no other library).

Fingerprint: 100 ms windows (Hann), magnitude spectrum, energy in 24 log-spaced bands from 60 Hz to 8 kHz, each
window's band vector as log energy with its mean removed, normalised. Similarity: the mean cosine of aligned windows,
best lag within +-1 s (1.0 = the same sound; a different song is far lower).

    python tools/harness/audioproof.py A.wav B.wav [C.wav ...]   similarity of every pair, and each file's level (RMS)
    python tools/harness/audioproof.py selftest                  synthetic tones: the same tone ~1, another tone low

The round-61 proof (build/r61/hooks/audio/fingerprint.py) passes a path when OFF vs ON < 0.8, ON vs ON2 > 0.98,
neither is silent, and the memory label of the started song is the spoiler's new map song."""
from __future__ import annotations

import itertools
import sys
import wave

import numpy as np


def load(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, w.getnchannels())
    return x.astype(np.float64).mean(axis=1), rate


def fingerprint(mono: np.ndarray, rate: int, win_s: float = 0.1, bands: int = 24, lo: float = 60.0,
                hi: float = 8000.0) -> np.ndarray:
    n = int(rate * win_s)
    k = len(mono) // n
    frames = mono[: k * n].reshape(k, n) * np.hanning(n)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    edges = np.geomspace(lo, min(hi, rate / 2 - 1), bands + 1)
    e = np.stack([spec[:, (freqs >= a) & (freqs < b)].sum(axis=1) for a, b in zip(edges[:-1], edges[1:])], axis=1)
    v = np.log10(e + 1e-3)
    v = v - v.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(norm == 0, 1, norm)


def similarity(fa: np.ndarray, fb: np.ndarray, max_lag: int = 10) -> tuple[float, int]:
    best = (-2.0, 0)
    for lag in range(-max_lag, max_lag + 1):
        a, b = fa[max(0, lag):], fb[max(0, -lag):]
        m = min(len(a), len(b))
        if m < 20:
            continue
        s = float((a[:m] * b[:m]).sum(axis=1).mean())
        if s > best[0]:
            best = (s, lag)
    return best


def rms(mono: np.ndarray) -> float:
    return float(np.sqrt((mono ** 2).mean()))


def selftest() -> int:
    rate = 32728
    t = np.arange(rate * 10) / rate
    a = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 660 * t)
    b = np.sin(2 * np.pi * 150 * t) + 0.5 * np.sin(2 * np.pi * 2500 * t)
    fa = fingerprint(a * 3000, rate)
    same = similarity(fa, fingerprint(np.roll(a, 1600) * 3000, rate))[0]
    other = similarity(fa, fingerprint(b * 3000, rate))[0]
    ok = same > 0.98 and other < 0.8
    print(f"audioproof selftest: same {same:.3f} other {other:.3f}", "OK" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv == ["selftest"]:
        return selftest()
    if len(argv) < 2:
        print(__doc__)
        return 2
    fp = {}
    for p in argv:
        mono, rate = load(p)
        fp[p] = fingerprint(mono, rate)
        print(f"{p}: {len(mono) / rate:.1f} s, rms {rms(mono):.1f}")
    for a, b in itertools.combinations(argv, 2):
        s, lag = similarity(fp[a], fp[b])
        print(f"{s:.4f} (lag {lag * 100} ms)  {a}  vs  {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

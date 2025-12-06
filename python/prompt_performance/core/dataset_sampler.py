"""
Dataset sampler with anti-overfitting strategies.

- Stratified by symbol/timeframe
- Enforces min_offset (skip N newest per symbol/timeframe)
- Non-overlapping samples across iterations
- Reproducible via random seed
- Growth schedule (e.g., [1,2,4,8]) images per symbol/timeframe

Relies on backtest_with_images.ImageSelector for image discovery and parsing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional, Iterable
import random
from pathlib import Path

from prompt_performance.backtest_with_images import ImageSelector, ImageInfo


class SamplerConfig:
    def __init__(
        self,
        symbols: List[str],
        timeframes: List[str],
        charts_dir: Path,
        min_offset: int = 100,
        growth: Optional[List[int]] = None,
        seed: int = 42,
    ) -> None:
        self.symbols = symbols
        self.timeframes = timeframes
        self.charts_dir = charts_dir
        self.min_offset = max(0, int(min_offset))
        self.growth = growth or [1, 2, 4, 8]
        self.seed = seed


class DatasetSampler:
    def __init__(self, cfg: SamplerConfig) -> None:
        self.cfg = cfg
        self._im = ImageSelector(charts_dir=str(cfg.charts_dir))
        self._rng = random.Random(cfg.seed)
        self._used: set[str] = set()  # filenames already sampled

    def _list_images(self) -> List[ImageInfo]:
        imgs = self._im.discover_images(symbols=None)
        # filter by symbols/timeframes if provided
        if self.cfg.symbols:
            imgs = [i for i in imgs if i.symbol in set(self.cfg.symbols)]
        if self.cfg.timeframes:
            imgs = [i for i in imgs if i.timeframe in set(self.cfg.timeframes)]
        # sort descending by timestamp (newest first) to apply offset later
        imgs.sort(key=lambda x: (x.symbol, x.timeframe, x.timestamp or 0), reverse=True)
        return imgs

    def _group_by_key(self, imgs: Iterable[ImageInfo]) -> Dict[Tuple[str, str], List[ImageInfo]]:
        buckets: Dict[Tuple[str, str], List[ImageInfo]] = {}
        for i in imgs:
            key = (i.symbol, i.timeframe)
            buckets.setdefault(key, []).append(i)
        return buckets

    def next_iteration(self, iteration_index: int) -> List[ImageInfo]:
        """
        Return the sampled ImageInfo list for an iteration.
        - Skips the newest min_offset images per (symbol,timeframe)
        - Selects N per key using the growth schedule
        - Ensures no overlap with previous iterations
        """
        imgs = self._list_images()
        buckets = self._group_by_key(imgs)
        k = self.cfg.growth[min(iteration_index, len(self.cfg.growth) - 1)]
        sample: List[ImageInfo] = []

        for key, arr in buckets.items():
            # apply offset per key
            eligible = [i for idx, i in enumerate(arr) if idx >= self.cfg.min_offset]
            # exclude previously used
            eligible = [i for i in eligible if i.filepath.name not in self._used]
            if not eligible:
                continue
            # random sample up to k
            n = min(k, len(eligible))
            choices = self._rng.sample(eligible, n)
            sample.extend(choices)

        # mark used
        for i in sample:
            self._used.add(i.filepath.name)
        return sample

    def used_filenames(self) -> List[str]:
        return sorted(self._used)


__all__ = ["SamplerConfig", "DatasetSampler"]


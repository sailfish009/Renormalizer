# -*- coding: utf-8 -*-
from enum import Enum
import logging

import scipy.linalg
import numpy as np

from ephMPS.utils.rk import RungeKutta


logger = logging.getLogger(__name__)


class BondOrderDistri(Enum):
    uniform = "uniform"
    center_gauss = "center gaussian"


class CompressConfig:
    def __init__(self, bondorder_distri=None, max_bondorder=None):
        self.use_threshold = True
        self._threshold = 0.001
        if bondorder_distri is not None:
            self.use_threshold = False
        else:
            bondorder_distri = BondOrderDistri.uniform
            max_bondorder = 1
        self.bond_order_distribution: BondOrderDistri = bondorder_distri
        self.max_bondorder = max_bondorder
        # the length should be len(mps) - 1, because on terminals bond orders are 1
        self.bond_orders: np.ndarray = np.array([])

    @property
    def threshold(self):
        return self._threshold

    @threshold.setter
    def threshold(self, v):
        if v <= 0:
            raise ValueError("non-positive threshold")
        elif v == 1:
            raise ValueError("ambiguous threshold (1)")
        else:
            self._threshold = v

    def set_bondorder(self, length, max_value=None):
        if max_value is None:
            max_value = self.max_bondorder
        else:
            self.max_bondorder = max_value
        self.use_threshold = False
        if self.bond_order_distribution == BondOrderDistri.uniform:
            self.bond_orders = np.full(length, max_value)
        else:
            assert length % 2 == 1
            half_length = length // 2
            x = np.arange(-half_length, half_length + 1)
            sigma = half_length / np.sqrt(np.log(max_value))
            seq = list(max_value * np.exp(-(x / sigma) ** 2))
            if length % 2 == 0:
                # should pop the middle
                seq.pop(half_length)
            self.bond_orders = np.int64(seq)
            self.bond_orders[self.bond_orders == 0] = 1  # avoid zeros

    def compute_m_trunc(self, sigma: np.ndarray, idx: int, l: bool) -> int:
        if self.use_threshold:
            assert 0 < self.threshold < 1
            # count how many sing vals < trunc
            normed_sigma = sigma / scipy.linalg.norm(sigma)
            # m_trunc=len([s for s in normed_sigma if s >trunc])
            m_trunc = np.sum(normed_sigma > self.threshold)
        else:
            if len(self.bond_orders) == 0:
                raise ValueError("Bond orders not initialized")
            # l means left canonicalised, sweep from right to left.
            # suppose we have 3 sites, the first idx is 2, then 1,
            # we need to access the second bond order (with idx 1)
            # and then first (with idx 0)
            # for r, indices = [0, 1], and we want to access [0, 1]
            # so no need to change
            bond_idx = idx - 1 if l else idx
            m_trunc = min(self.bond_orders[bond_idx], len(sigma))
        assert m_trunc != 0
        return m_trunc

    def update(self, other: "CompressConfig"):
        # use the stricter of the two
        if self.use_threshold != other.use_threshold:
            raise ValueError("Can't update configs with different standard")
        if self.use_threshold:
            # look for minimum
            self.threshold = min(self.threshold, other.threshold)
        else:
            # look for maximum
            self.bond_orders = np.maximum(self.bond_orders, other.bond_orders)

    def relax(self):
        # relax the two criteria simultaneously
        self.threshold = min(
            self.threshold * 3, 0.9
        )  # can't set to 1 which is ambiguous
        self.bond_orders = np.maximum(
            np.int64(self.bond_orders * 0.8), np.full_like(self.bond_orders, 2)
        )

    def copy(self):
        new = self.__class__.__new__(self.__class__)
        # shallow copies
        new.__dict__ = self.__dict__.copy()
        # deep copy
        new.bond_orders = self.bond_orders.copy()
        return new


class OptimizeConfig:
    def __init__(self, procedure=None):
        if procedure is None:
            self.procedure = [[10, 0.4], [20, 0.2], [30, 0.1], [40, 0], [40, 0]]
        else:
            self.procedure = procedure
        self.method = "2site"
        self.nroots = 1
        self.inverse = 1.0
        # for dmrg-hartree hybrid to check converge. Not to confuse with compress threshold
        self.niterations = 20
        self.dmrg_thresh = 1e-5
        self.hartree_thresh = 1e-5


class EvolveMethod(Enum):
    prop_and_compress = "P&C"
    tdvp_ps = "TDVP_PS"
    tdvp_mctdh = "TDVP_MCTDH"
    tdvp_mctdh_new = "TDVP_MCTDHnew"


class EvolveConfig:
    def __init__(
        self,
        scheme: EvolveMethod = EvolveMethod.prop_and_compress,
        rk_config: RungeKutta = None,
    ):
        self.scheme = scheme
        # tdvp also requires prop and compress
        if rk_config is None:
            self.rk_config: RungeKutta = RungeKutta()
        else:
            self.rk_config: RungeKutta = rk_config
        self.prop_method = "C_RK4"
        if self.scheme == EvolveMethod.prop_and_compress:
            self.expected_bond_order = None
        else:
            self.expected_bond_order = 50

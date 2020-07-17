# -*- coding: utf-8 -*-
# Author: Jiajun Ren <jiajunren0522@gmail.com>
#         Weitang Li <liwt31@163.com>

import os

import pytest

from renormalizer.model import Phonon, Mol, HolsteinModel
from renormalizer.mps import Mps, Mpo, ThermalProp, MpDm, MpDmFull
from renormalizer.mps.gs import optimize_mps
from renormalizer.transport import ChargeDiffusionDynamics
from renormalizer.utils import Quantity
from renormalizer.utils import (
    BondDimDistri,
    CompressCriteria,
    CompressConfig,
    EvolveMethod,
    EvolveConfig,
)
from renormalizer.transport.tests.band_param import (
    band_limit_mol_list,
    assert_band_limit,
    low_t,
)

import numpy as np


def test_zt_init_state():
    ph = Phonon.simple_phonon(Quantity(1), Quantity(1), 10)
    mol_list = HolsteinModel([Mol(Quantity(0), [ph])], Quantity(0), )
    mpo = Mpo(mol_list)
    mps = Mps.random(mol_list, 1, 10)
    optimize_mps(mps, mpo)
    ct = ChargeDiffusionDynamics(mol_list)
    assert mps.angle(ct.latest_mps) == pytest.approx(1)


def test_ft_init_state():
    ph = Phonon.simple_phonon(Quantity(1), Quantity(1), 10)
    mol_list = HolsteinModel([Mol(Quantity(0), [ph])], Quantity(0), )
    temperature = Quantity(0.1)
    mpo = Mpo(mol_list)
    init_mpdm = MpDm.max_entangled_ex(mol_list)
    tp = ThermalProp(init_mpdm, mpo, space="EX", exact=True)
    tp.evolve(nsteps=20, evolve_time=temperature.to_beta() / 2j)
    ct = ChargeDiffusionDynamics(mol_list, temperature=temperature)
    tp_mpdm = MpDmFull.from_mpdm(tp.latest_mps)
    ct_mpdm = MpDmFull.from_mpdm(ct.latest_mps)
    assert tp_mpdm.angle(ct_mpdm) == pytest.approx(1)


@pytest.mark.parametrize(
    "method, evolve_dt, nsteps, rtol",
    (
        (EvolveMethod.prop_and_compress, 4, 25, 1e-3),
        (EvolveMethod.tdvp_ps, 2, 50, 1e-3),
    ),
)
@pytest.mark.parametrize("scheme", (3, 4))
def test_bandlimit_zero_t(method, evolve_dt, nsteps, rtol, scheme):
    evolve_config = EvolveConfig(method)
    ct = ChargeDiffusionDynamics(
        band_limit_mol_list.switch_scheme(scheme),
        evolve_config=evolve_config,
    )
    ct.stop_at_edge = True
    ct.evolve(evolve_dt, nsteps)
    assert_band_limit(ct, rtol)


@pytest.mark.parametrize(
    "method", (EvolveMethod.prop_and_compress, EvolveMethod.tdvp_ps)
)
def test_adaptive_zero_t(method):
    np.random.seed(0)
    evolve_config = EvolveConfig(method=method, guess_dt=0.1, adaptive=True)
    ct = ChargeDiffusionDynamics(
        band_limit_mol_list, evolve_config=evolve_config, stop_at_edge=True
    )
    ct.evolve(evolve_dt=5.)
    assert_band_limit(ct, 1e-2)


def test_gaussian_bond_dim():
    compress_config = CompressConfig(
        criteria=CompressCriteria.fixed,
        bonddim_distri=BondDimDistri.center_gauss,
        max_bonddim=10,
    )
    evolve_config = EvolveConfig(guess_dt=0.1, adaptive=True)
    ct = ChargeDiffusionDynamics(
        band_limit_mol_list,
        compress_config=compress_config,
        evolve_config=evolve_config,
    )
    ct.stop_at_edge = True
    ct.evolve(evolve_dt=2.)
    assert_band_limit(ct, 1e-2)


def assert_iterable_equal(i1, i2):
    if isinstance(i1, str):
        assert i1 == i2
        return
    if not hasattr(i1, "__iter__"):
        if isinstance(i1, float):
            assert i1 == pytest.approx(i2)
        else:
            assert i1 == i2
        return
    for ii1, ii2 in zip(i1, i2):
        assert_iterable_equal(ii1, ii2)



@pytest.mark.parametrize(
    "mol_num, j_constant_value, elocalex_value, ph_info, ph_phys_dim, evolve_dt, nsteps",
    ([5, 0.8, 3.87e-3, [[1400, 17]], 4, 2, 50],),
)
def test_similar(
    mol_num, j_constant_value, elocalex_value, ph_info, ph_phys_dim, evolve_dt, nsteps
):
    ph_list = [
        Phonon.simple_phonon(
            Quantity(omega, "cm^{-1}"), Quantity(displacement, "a.u."), ph_phys_dim
        )
        for omega, displacement in ph_info
    ]
    mol_list = HolsteinModel([Mol(Quantity(elocalex_value, "a.u."), ph_list)] * mol_num,
                             Quantity(j_constant_value, "eV"), )
    ct1 = ChargeDiffusionDynamics(mol_list)
    ct1.evolve(evolve_dt, nsteps)
    ct2 = ChargeDiffusionDynamics(mol_list)
    ct2.evolve(evolve_dt + 1e-5, nsteps)
    assert ct1.is_similar(ct2)


@pytest.mark.parametrize(
    "mol_num, j_constant_value, elocalex_value, ph_info, ph_phys_dim, evolve_dt, nsteps",
    ([5, 0.8, 3.87e-3, [[1400, 17]], 4, 2, 50],),
)
def test_evolve(
    mol_num, j_constant_value, elocalex_value, ph_info, ph_phys_dim, evolve_dt, nsteps
):
    ph_list = [
        Phonon.simple_phonon(
            Quantity(omega, "cm^{-1}"), Quantity(displacement, "a.u."), ph_phys_dim
        )
        for omega, displacement in ph_info
    ]
    mol_list = HolsteinModel([Mol(Quantity(elocalex_value, "a.u."), ph_list)] * mol_num,
                             Quantity(j_constant_value, "eV"), )
    ct1 = ChargeDiffusionDynamics(mol_list, stop_at_edge=False)
    half_nsteps = nsteps // 2
    ct1.evolve(evolve_dt, half_nsteps)
    ct1.evolve(evolve_dt, nsteps - half_nsteps)
    ct2 = ChargeDiffusionDynamics(mol_list, stop_at_edge=False)
    ct2.evolve(evolve_dt, nsteps)
    assert ct1.is_similar(ct2)
    assert_iterable_equal(ct1.get_dump_dict(), ct2.get_dump_dict())

    # test dump
    ct2.dump_dir = "."
    ct2.job_name = "test"
    ct2.dump_dict()
    os.remove("test.npz")


@pytest.mark.parametrize(
    "mol_num, j_constant_value, elocalex_value, ph_info, ph_phys_dim, evolve_dt, nsteps",
    ([3, 1, 3.87e-3, [[1e-5, 1e-5]], 2, 2, 50],),
)
@pytest.mark.parametrize("scheme", (3, 4))
def test_band_limit_finite_t(
    mol_num,
    j_constant_value,
    elocalex_value,
    ph_info,
    ph_phys_dim,
    evolve_dt,
    nsteps,
    scheme,
):
    ph_list = [
        Phonon.simple_phonon(
            Quantity(omega, "cm^{-1}"), Quantity(displacement, "a.u."), ph_phys_dim
        )
        for omega, displacement in ph_info
    ]
    mol_list = HolsteinModel([Mol(Quantity(elocalex_value, "a.u."), ph_list)] * mol_num,
                             Quantity(j_constant_value, "eV"), )
    ct1 = ChargeDiffusionDynamics(mol_list, stop_at_edge=False)
    ct1.evolve(evolve_dt, nsteps)
    ct2 = ChargeDiffusionDynamics(mol_list, temperature=low_t, stop_at_edge=False)
    ct2.evolve(evolve_dt, nsteps)
    assert ct1.is_similar(ct2)
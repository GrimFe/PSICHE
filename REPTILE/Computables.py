from dataclasses import dataclass
from REPTILE.FissionFragmentSpectrum import FissionFragmentSpectrum
from REPTILE.EffectiveMass import EffectiveMass
from REPTILE.ReactionRate import ReactionRate
from REPTILE.utils import ratio_v_u, product_v_u, _make_df

import pandas as pd
import numpy as np
import warnings

__all__ = ['NormalizedFissionFragmentSpectrum',
           'Traverse']


def average_v_u(df):
    v = df.value.mean()
    u = sum(df.uncertainty **2) / len(df.uncertainty)
    return v, u

@dataclass(slots=True)
class Computable:
    def compute(self) -> None:
        """
        Placeholder for inheriting classes.
        """
        return None


@dataclass(slots=True)
class NormalizedFissionFragmentSpectrum(Computable):
    fission_fragment_spectrum: FissionFragmentSpectrum
    effective_mass: EffectiveMass
    power_monitor: ReactionRate

    def __post_init__(self) -> None:
        self._check_consistency()

    def _check_consistency(self) -> None:
        """
        Checks the consistency of:
            - experiment_id
            - detector_id
            - deposit_id
        among self.fission_fragment_spectrum
        and also checks:
            - R channel
        among self.fission_fragment_spectrum and effective_mass
        via _check_ch_equality(tolerance=0.01).

        Raises
        ------
        Exception
            If there are inconsistencies among the IDs or R channel values.
        """
        if not self.fission_fragment_spectrum.detector_id == self.effective_mass.detector_id:
            raise Exception('Inconsistent detectors among FissionFragmentSpectrum ans EffectiveMass')
        if not self.fission_fragment_spectrum.deposit_id == self.effective_mass.deposit_id:
            raise Exception('Inconsistent deposits among FissionFragmentSpectrum and EffectiveMass')
        if not self.fission_fragment_spectrum.experiment_id == self.power_monitor.experiment_id:
            raise Exception('Inconsitent experiments among FissionFragmentSpectrum and ReactionRate')
        if not self._check_ch_equality():
            warnings.warn(f"""The channel values differ more than 1%; at spectrum half maximum they worth:
                          measurement: {self.fission_fragment_spectrum.get_R(self.effective_mass.bins).channel}
                          calibration: {self.effective_mass.R_channel}
                          relative difference (C-M)/C: {(self.fission_fragment_spectrum.get_R(self.effective_mass.bins).channel
                                                        - self.effective_mass.R_channel)
                                                        / self.effective_mass.R_channel * 100} %""")

    def _check_ch_equality(self, tolerance:float =0.01) -> bool:
        """
        Checks consistency of the R channels of `self.fission_fragment_spectrum` and
        `self.effective_mass` within a specified tolerance.
        The check happens only if the binning of the two objects is the same.
        
        Parameters
        ----------
        tolerance : float, optional
            The acceptable relative difference between the R channel of
            `self.fission_fragment_spectrum` and `self.effective_mass`.
            Defaults to 0.01.

        Returns
        -------
        bool
            Indicating whether the relative difference between the R channels is within tolerance.
        """
        if self.fission_fragment_spectrum.data.channel.max() == self.effective_mass.bins:
            check = abs(self.fission_fragment_spectrum.get_R(self.effective_mass.bins).channel
            - self.effective_mass.R_channel) / self.effective_mass.R_channel < tolerance
        else:
            check = True
        return check 

    @property
    def measurement_id(self) -> str:
        """
        The measurement ID associated with the fission fragment spectrum.

        Returns
        -------
        str
            The measurement ID attribute of the associated `FissionFragmentSpectrum`.
        """
        return self.fission_fragment_spectrum.measurement_id
    
    @property
    def campaign_id(self) -> str:
        """
        The campaign ID associated with the fission fragment spectrum.

        Returns
        -------
        str
            The campaign ID attribute of the associated `FissionFragmentSpectrum`.
        """
        return self.fission_fragment_spectrum.campaign_id
    
    @property
    def experiment_id(self) -> str:
        """
        The experiment ID associated with the fission fragment spectrum.

        Returns
        -------
        str
            The experiment ID attribute of the associated `FissionFragmentSpectrum`.
        """
        return self.fission_fragment_spectrum.experiment_id
    
    @property
    def location_id(self) -> str:
        """
        The location ID associated with the fission fragment spectrum.

        Returns
        -------
        str
            The location ID attribute of the associated `FissionFragmentSpectrum`.
        """
        return self.fission_fragment_spectrum.location_id

    @property
    def deposit_id(self):
        """
        The deposit ID associated with the fission fragment spectrum.

        Returns
        -------
        str
            The deposit ID attribute of the associated `FissionFragmentSpectrum`.
        """
        return self.fission_fragment_spectrum.deposit_id

    @property
    def _time_normalization(self) -> pd.DataFrame:
        """
        The time normalization and correction to be multiplied by the
        fission fragment spectrum per unit mass.

        Returns
        -------
        pd.DataFrame
            with normalization value and uncertainty
        """
        v = self.fission_fragment_spectrum.real_time / self.fission_fragment_spectrum.life_time**2
        u = 0
        return _make_df(v, u)

    @property
    def _power_normalization(self) -> pd.DataFrame:
        """
        The power normalization to be multiplied by the fission fragment
        spectrum per unit mass.

        Returns
        -------
        pd.DataFrame
            with normalization value and uncertainty
        """
        start_time = self.fission_fragment_spectrum.start_time
        duration = int(self.fission_fragment_spectrum.real_time)
        v, u = ratio_v_u(_make_df(1, 0), self.power_monitor.average(start_time, duration))
        return _make_df(v, u)

    @property
    def per_unit_mass(self) -> pd.DataFrame:
        """
        The tabulated ratio of FFS.integrate() / EM.integral, integrated from
        10 discrimination levels computed as a function of the R channel.
        """
        ffs, em = self.fission_fragment_spectrum, self.effective_mass
        bins = em.bins
        v, u = ratio_v_u(ffs.integrate(bins), em.integral)
        df = pd.concat([_make_df(i, j) for i, j in zip(v, u)], ignore_index=True)
        data = pd.DataFrame({'channel fission fragment spectrum': ffs.integrate(bins).channel,
                             'channel effective mass': em.integral.channel,
                             'value': df.value,
                             'uncertainty': df.uncertainty,
                             'uncertainty [%]': df['uncertainty [%]']})
        return data

    @property
    def per_unit_mass_and_time(self) -> pd.DataFrame:
        """
        The integrated FFS normalized per unit mass and time.
        """
        ffs, em = self.fission_fragment_spectrum, self.effective_mass
        bins = em.bins
        data = pd.concat([_make_df(x[0], x[1]) for x in
                          [product_v_u([self._time_normalization.set_index(pd.Index([i])),
                                        self.per_unit_mass.loc[i].to_frame().T]) for i in
                                        self.per_unit_mass.index]],
                         ignore_index=True).assign(A=ffs.integrate(bins).channel,
                                                   B=em.integral.channel)
        data = data.rename({'A': 'channel fission fragment spectrum', 'B': 'channel effective mass'}, axis=1)
        return data[['channel fission fragment spectrum', 'channel effective mass',
                    'value', 'uncertainty', 'uncertainty [%]']]

    @property
    def per_unit_mass_and_power(self) -> pd.DataFrame:
        """
        The integrated FFS normalized per unit mass and power.
        """
        ffs, em = self.fission_fragment_spectrum, self.effective_mass
        bins = em.bins
        data = pd.concat([_make_df(x[0], x[1]) for x in
                          [product_v_u([self._power_normalization.set_index(pd.Index([i])),
                                        self.per_unit_mass.loc[i].to_frame().T]) for i in
                                        self.per_unit_mass.index]],
                         ignore_index=True).assign(A=ffs.integrate(bins).channel,
                                                   B=em.integral.channel)
        data = data.rename({'A': 'channel fission fragment spectrum', 'B': 'channel effective mass'}, axis=1)
        return data[['channel fission fragment spectrum', 'channel effective mass',
                    'value', 'uncertainty', 'uncertainty [%]']]

    def plateau(self, int_tolerance: float =.01, ch_tolerance: float =.01) -> pd.DataFrame:
        """
        Computes the reaction rate per unit mass.

        Parameters
        ----------
        int_tolerance : float, optional
            Tolerance for the integration check, by default 0.01.
        ch_tolerance : float, optional
            Tolerance for the channel check, by default 0.01.

        Returns
        -------
        pd.DataFrame
            DataFrame containing the reaction rate per unit mass.

        Raises
        ------
        ValueError
            If the channel values differ beyond the specified tolerance.
        """
        data = self.per_unit_mass
        # check where the values in the mass-normalized count rate converge withing tolerance
        close_values = data[np.isclose(data.value, np.roll(data.value, shift=1), rtol=int_tolerance)]
        if close_values.shape[0] == 0:
            raise Exception("No convergence found with the given tolerance on the integral.")
        # consider only values where the convergence is observed in two neighboring channels, i.e. atol=1
        plateau = close_values[np.isclose(close_values.index, np.roll(close_values.index, shift=1), atol=1)]
        if plateau.shape[0] == 0:
            raise Exception("No convergence found in neighbouring channels.")
        # check the channels in which value does not differ more than ch_tolerance from the calibration ones
        plateau = plateau[abs(plateau['channel fission fragment spectrum'] - plateau['channel effective mass'])
                / plateau['channel effective mass'] < ch_tolerance]
        if plateau.shape[0] == 0:
            raise Exception("No convergence found with the given tolerance on the channel.")
        return plateau.iloc[0]

    def compute(self, *args, **kwargs) -> pd.DataFrame:
        """
        Computes the reaction rate.

        Parameters
        ----------
        *args : Any
            Positional arguments to be passed to the `self.plateau()` method.
        **kwargs : Any
            Keyword arguments to be passed to the `self.plateau()` method.

        Returns
        -------
        pd.DataFrame
            DataFrame containing the reaction rate.

        Examples
        --------
        >>> ffs = FissionFragmentSpectrum(data=pd.DataFrame({'value': [1.0, 2.0, 3.0], 'uncertainty': [0.1, 0.2, 0.3]}),
        ...                               detector_id='D1', deposit_id='Dep1', experiment_id='Exp1')
        >>> em = EffectiveMass(data=pd.DataFrame({'value': [0.5, 0.6, 0.7], 'uncertainty': [0.05, 0.06, 0.07]}),
        ...                    detector_id='D1', deposit_id='Dep1')
        >>> pm = ReactionRate(data=pd.DataFrame({'value': [10, 20, 30], 'uncertainty': [1, 2, 3]}), experiment_id='Exp1')
        >>> rr = NormalizedFissionFragmentSpectrum(fission_fragment_spectrum=ffs, effective_mass=em, power_monitor=pm)
        >>> rr.compute()
            value  uncertainty
        0  35.6    2.449490
        """
        v, u = product_v_u([self.plateau(*args, **kwargs), self._power_normalization, self._time_normalization])
        return _make_df(v, u)

@dataclass(slots=True)
class Traverse(Computable):
    def compute(self) -> None:
        return super().compute()

# @dataclass
# class AverageNormalizedFissionFragmentSpectrum:
#     fission_fragment_spectra: FissionFragmentSpectra
#     effective_mass: EffectiveMass
#     power_monitor: ReactionRate

#     @property
#     def campaign_id(self):
#         """
#         The campaign ID associated with the last fission fragment spectrum.

#         Returns
#         -------
#         str
#             The campaign ID attribute of the associated `FissionFragmentSpectrum`.

#         """
#         return self.fission_fragment_spectra[-1].campaign_id
    
#     @property
#     def experiment_id(self) -> str:
#         """
#         The experiment ID associated with the last fission fragment spectrum.

#         Returns
#         -------
#         str
#             The experiment ID attribute of the associated `FissionFragmentSpectrum`.

#         """
#         return self.fission_fragment_spectra[-1].experiment_id
    
#     @property
#     def location_id(self) -> str:
#         """
#         The location ID associated with the last fission fragment spectrum.

#         Returns
#         -------
#         str
#             The location ID attribute of the associated `FissionFragmentSpectrum`.

#         """
#         return self.fission_fragment_spectra[-1].location_id

#     @property
#     def deposit_id(self):
#         """
#         The deposit ID associated with the last fission fragment spectrum.

#         Returns
#         -------
#         str
#             The deposit ID attribute of the associated `FissionFragmentSpectrum`.

#         """
#         return self.fission_fragment_spectra[-1].deposit_id

#     def compute(self, *args, **kwargs):
#         """
#         Computes the average of multiple reaction rates.

#         Returns
#         -------
#         pd.DataFrame
#             DataFrame containing the average reaction rate.

#         Examples
#         --------
#         >>> ffs1 = FissionFragmentSpectrum(data=pd.DataFrame({'value': [1.0, 2.0, 3.0], 'uncertainty': [0.1, 0.2, 0.3]}),
#         ...                                detector_id='D1', deposit_id='Dep1', experiment_id='Exp1')
#         >>> em1 = EffectiveMass(data=pd.DataFrame({'value': [0.5, 0.6, 0.7], 'uncertainty': [0.05, 0.06, 0.07]}),
#         ...                     detector_id='D1', deposit_id='Dep1')
#         >>> pm1 = ReactionRate(data=pd.DataFrame({'value': [10, 20, 30], 'uncertainty': [1, 2, 3]}), experiment_id='Exp1')
#         >>> rr1 = NormalizedFissionFragmentSpectrum(fission_fragment_spectrum=ffs1, effective_mass=em1, power_monitor=pm1)

#         >>> ffs2 = FissionFragmentSpectrum(data=pd.DataFrame({'value': [2.0, 4.0, 6.0], 'uncertainty': [0.2, 0.4, 0.6]}),
#         ...                                detector_id='D1', deposit_id='Dep1', experiment_id='Exp1')
#         >>> em2 = EffectiveMass(data=pd.DataFrame({'value': [0.4, 0.5, 0.6], 'uncertainty': [0.04, 0.05, 0.06]}),
#         ...                     detector_id='D1', deposit_id='Dep1')
#         >>> pm2 = ReactionRate(data=pd.DataFrame({'value': [15, 25, 35], 'uncertainty': [1.5, 2.5, 3.5]}), experiment_id='Exp1')
#         >>> rr2 = NormalizedFissionFragmentSpectrum(fission_fragment_spectrum=ffs2, effective_mass=em2, power_monitor=pm2)

#         >>> arr = AverageNormalizedFissionFragmentSpectrum(reaction_rates=[rr1, rr2])
#         >>> arr.compute()
#             value  uncertainty
#         0  43.366667  3.162278
#         """
#         data = []
#         for ffs in self.fission_fragment_spectra.spectra:
#             data.append(NormalizedFissionFragmentSpectrum(ffs,
#                                      self.effective_mass,
#                                      self.power_monitor
#                                      ).compute(*args, **kwargs
#                                                ).assign(measurement=ffs.measurement_id))
#         data = pd.concat(data)
#         v, u = average_v_u(data)
#         return _make_df(v, u)

from collections.abc import Iterable
from dataclasses import dataclass
import numpy as np
import pandas as pd
import linecache
from datetime import datetime, timedelta
import warnings

from REPTILE.utils import ratio_v_u, _make_df, integral_v_u

__all__ = [
    "ReactionRate",
    "ReactionRates"]

@dataclass(slots=True)
class ReactionRate:
    data: pd.DataFrame
    start_time: datetime
    campaign_id: str
    experiment_id: str
    detector_id: str

    def average(self, start_time: datetime, duration: int) -> pd.DataFrame:
        """
        Calculate the average value and uncertainty of a time series data within a specified duration.

        Parameters
        ----------
        start_time : datetime
            The starting time for the data to be analyzed.
        duration : int
            The length of time in seconds for which the average is calculated.

        Returns
        -------
        pd.DataFrame
            DataFrame containing:
            - 'value': The average value of the data within the specified time range.
            - 'uncertainty': The uncertainty value, calculated as 1/sqrt(N).

        Examples
        --------
        >>> from datetime import datetime
        >>> data = pd.DataFrame({'Time': pd.date_range('2021-01-01', periods=100, freq='S'),
                                 'value': np.random.rand(100)})
        >>> pm = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                              campaign_id='C1', experiment_id='E1', detector_id='M1')
        >>> avg_df = pm.average(datetime(2021, 1, 1, 0, 0, 30), 10)
        >>> print(avg_df)
        """
        end_time = start_time + timedelta(seconds=duration)
        series = self.data.query("Time > @start_time and Time <= @end_time")
        v, u = integral_v_u(series.value)
        return _make_df(v / duration, u / duration)

    def integrate(self, timebase: int, start_time: datetime | None = None) -> pd.DataFrame:
        """
        Integrate data over a specified timebase starting from a given start time.

        Parameters
        ----------
        timebase : int
            The interval of time in seconds over which to calculate the average. This interval is used to group the data for averaging.
        start_time : datetime, optional
            The starting time for the integration process. Defaults to `self.start_time`.

        Returns
        -------
        pd.DataFrame
            DataFrame containing:
            - 'value': The average value of the data within the specified time range.
            - 'uncertainty': The uncertainty value, calculated as 1/sqrt(N).

        Examples
        --------
        >>> from datetime import datetime
        >>> data = pd.DataFrame({'Time': pd.date_range('2021-01-01', periods=100, freq='S'),
                                 'value': np.random.rand(100)})
        >>> pm = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                              campaign_id='C1', experiment_id='E1', detector_id='M1')
        >>> integrated_df = pm.integrate(10)
        >>> print(integrated_df)
        """
        start_time_ = self.start_time if start_time is None else start_time
        out = []
        while start_time_ < self.data.Time.max():
            out.append(self.average(start_time_, timebase))
            start_time_ = start_time_ + timedelta(seconds=timebase)
        return pd.concat(out, ignore_index=True)

    def per_unit_power(self, monitor) -> pd.DataFrame:
        """
        Normalizes the raction rate to a power monitor.

        Parameters
        ----------
        monitor : ReactionRate
        """
        pass

    @classmethod
    def from_ascii(cls, file: str, detector: int):
        """
        Placeholder method to create a `ReactionRate` instance from an ASCII file.

        Parameters
        ----------
        file : str
            Path to the ASCII file.
        detector : int
            Detector number in the ASCII file.

        Returns
        -------
        ReactionRate
            A new `ReactionRate` instance.
        """
        start_time = datetime.strptime(linecache.getline(file, 1), "%d-%m-%Y %H:%M:%S\n")
        read = pd.read_csv(file, sep='\t', skiprows=[0,1], decimal=',')
        read["Time"] = read["Time"].apply(lambda x: start_time + timedelta(seconds=x))
        campaign_id, experiment_id = file.split('\\')[-1].split('_')
        out = cls(read[["Time", f"Det {detector}"]].rename(columns={f"Det {detector}": "value"}),
                  start_time=start_time,
                  campaign_id=campaign_id,
                  experiment_id=experiment_id,
                  detector_id=f"Det {detector}")
        return out

@dataclass(slots=True)
class ReactionRates:
    monitors: list[ReactionRate]

    def __post_init__(self) -> None:
        self._check_consistency()

    def _check_consistency(self, time_tolerance: timedelta=timedelta(seconds=60),
                           timebase: int=100, sigma=1) -> None:
        """
        Check the consistency of time and curve data with specified parameters.

        Parameters
        ----------
        time_tolerance : timedelta, optional
            Parameter for `self._check_time_consistency`. Defaults to 60 seconds.
        timebase : int, optional
            Parameter for `self._check_curve_consistency`. Defaults to 100.
        sigma : int, optional
            Parameter for `self._check_curve_consistency`. Defaults to 1.

        Examples
        --------
        >>> data = pd.DataFrame({'Time': pd.date_range('2021-01-01', periods=100, freq='S'),
                                 'value': np.random.rand(100)})
        >>> pm1 = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                               campaign_id='C1', experiment_id='E1', detector_id='M1')
        >>> pm2 = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                               campaign_id='C1', experiment_id='E1', detector_id='M2')
        >>> pms = ReactionRates(monitors=[pm1, pm2])
        >>> pms._check_consistency()
        """
        must = ['campaign_id', 'experiment_id']
        for attr in must:
            if not all([getattr(m, attr) == getattr(self.monitors[0], attr) for m in self.monitors]):
                raise Exception(f"Inconsistent {attr} among different ReactionRate instances.")
        self._check_time_consistency(time_tolerance)
        self._check_curve_consistency(timebase, sigma)

    def _check_time_consistency(self, time_tolerance: timedelta) -> None:
        """
        Check if the start times of power monitors are consistent within a given time tolerance.

        Parameters
        ----------
        time_tolerance : timedelta
            The maximum allowable difference in time between the start times of the power monitors in `self.monitors`.

        Examples
        --------
        >>> data = pd.DataFrame({'Time': pd.date_range('2021-01-01', periods=100, freq='S'),
                                 'value': np.random.rand(100)})
        >>> pm1 = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                               campaign_id='C1', experiment_id='E1', detector_id='M1')
        >>> pm2 = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                               campaign_id='C1', experiment_id='E1', detector_id='M2')
        >>> pms = ReactionRates(monitors=[pm1, pm2])
        >>> pms._check_time_consistency(timedelta(seconds=60))
        """
        ref = self.monitors[0].start_time
        for monitor in self.monitors:
            if not abs(monitor.start_time - ref) < time_tolerance:
                warnings.warn(f"Power monitor start time difference > {time_tolerance}")

    def _check_curve_consistency(self, timebase: int, sigma: int=1) -> None:
        """
        Compare data from multiple monitors to check for consistency within a sigma-uncertainty tolerance, based on a specified timebase.

        Parameters
        ----------
        timebase : int
            The time interval in seconds for grouping the data. This parameter determines how the data are aggregated and compared between different monitors.
        sigma : int, optional
            The uncertainty associated with the measurements. It is used to calculate the tolerance for checking the consistency between different power monitors. The tolerance is computed as the average uncertainty on the ratio of values between two monitors. Defaults to 1.

        Examples
        --------
        >>> data = pd.DataFrame({'Time': pd.date_range('2021-01-01', periods=100, freq='S'),
                                 'value': np.random.rand(100)})
        >>> pm1 = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                               campaign_id='C1', experiment_id='E1', detector_id='M1')
        >>> pm2 = ReactionRate(data=data, start_time=datetime(2021, 1, 1), 
                               campaign_id='C1', experiment_id='E1', detector_id='M2')
        >>> pms = ReactionRates(monitors=[pm1, pm2])
        >>> pms._check_curve_consistency(10, 1)
        """
        ref = self.monitors[0].data.groupby(pd.Grouper(key="Time", freq=f'{timebase}s', closed='right')
                                            ).agg('sum').reset_index()
        ref['uncertainty'] = np.sqrt(ref['value'])  # absolute
        ref['value'] = ref['value'] / timebase
        for monitor in self.monitors[1:]:
            compute = monitor.data.groupby(pd.Grouper(key="Time", freq=f'{timebase}s', closed='right')
                                            ).agg('sum').reset_index()
            compute['uncertainty'] = np.sqrt(compute['value'])  # absolute
            compute['value'] = compute['value'] / timebase
            # filtering noise below 100 counts in time
            start = max(ref.query('value >= 100').Time.min(), compute.query('value >= 100').Time.min())
            end = min(ref.query('value >= 100').Time.max(), compute.query('value >= 100').Time.max())
            qs = "Time >= @start and Time <= @end"
            v, u = ratio_v_u(compute.query(qs), ref.query(qs))
            # tolerance is scalar, therefore it is computed as average uncertainty on the ratio
            tol = np.mean(sigma * u)  # absolute
            if not (np.isclose(v, np.roll(v, shift=1), atol=tol)).all():
                raise Exception(f"Power monitor {monitor.detector_id} inconsistent with {self.monitors[0].detector_id}")

    @property
    def best(self) -> ReactionRate:
        """
        Returns the power monitor with the highest sum value.

        Returns
        -------
        ReactionRate
            Power monitor with the highest integral count.

        Examples
        --------
        >>> pm = ReactionRate(...)
        >>> best_pm = pm.best
        """
        max = self.monitors[0].data.value.sum()
        out = self.monitors[0]
        for monitor in self.monitors[1:]:
            if monitor.data.value.sum() > max:
                out = monitor
        return out

    @classmethod
    def from_ascii(cls, file: str, detectors: Iterable[int]):
        """
        Creates an instance of ReactionRate using data extracted from an ASCII file.

        The ASCII file should contain columns of data including timestamps and power readings.

        The filename is supposed to be formatted as:
        {Campaign}_{experiment}.txt

        Parameters
        ----------
        file : str
            Path to the ASCII file containing the power monitor data.
        detectors : Iterable[int]
            Detector numbers to read from the ASCII file.

        Returns
        -------
        ReactionRate
            An instance of the ReactionRate class initialized with the data from the ASCII file.

        Example
        -------
        Consider an ASCII file `power_data.txt` with the following content:

        ```
        timestamp,power
        2023-01-01 00:00:00,100
        2023-01-01 01:00:00,150
        2023-01-01 02:00:00,200
        ```

        You can create a ReactionRate instance from this file as follows:

        ```python
        from REPTILE.ReactionRate import ReactionRate

        power_monitor = ReactionRate.from_ascii('path/to/power_data.txt', experiment_id='EXP123')
        print(power_monitor.data)
        ```

        This will output:

        ```
                    timestamp  power
        0 2023-01-01 00:00:00    100
        1 2023-01-01 01:00:00    150
        2 2023-01-01 02:00:00    200
        ```

        Note
        ----
        Ensure that the file path provided is correct and that the file format matches the expected structure.
        """
        out = []
        for d in detectors:
            out.append(ReactionRate.from_ascii(file, d))
        return cls(out)
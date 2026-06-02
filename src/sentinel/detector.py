"""Anomaly detector behind a SageMaker-swappable interface.

``AnomalyDetector`` is the abstraction the rest of the Sentinel codes against.
The active local implementation is :class:`LocalIsolationForestDetector`
(scikit-learn ``IsolationForest``). The production implementation is
:class:`SageMakerRandomCutForestDetector`, which uses Amazon SageMaker Random
Cut Forest via batch transform - it shares the exact same interface so the swap
is a one-line change in :func:`build_detector` (``DETECTOR_BACKEND=sagemaker``).

Both expose RCF-style scores: higher means more anomalous, and the local
detector is normalised to a sigma scale so the ``ANOMALY_THRESHOLD`` default of
3.0 (~3 sigma) carries the same meaning across backends.
"""

from __future__ import annotations

import abc

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class AnomalyDetector(abc.ABC):
    """Common interface for the SageMaker-swappable anomaly detectors."""

    @abc.abstractmethod
    def fit(self, x: np.ndarray) -> "AnomalyDetector":
        """Train on a baseline feature matrix (rows = window feature vectors)."""

    @abc.abstractmethod
    def score(self, x: np.ndarray) -> np.ndarray:
        """Return one RCF-style anomaly score per row (higher = more anomalous)."""


class LocalIsolationForestDetector(AnomalyDetector):
    """Local stand-in for SageMaker RCF using scikit-learn IsolationForest.

    Features are log1p-compressed (counts and byte volumes span orders of
    magnitude) then standardised. Raw IsolationForest anomaly scores are
    converted to a sigma scale relative to the training distribution so the
    threshold semantics match SageMaker RCF.
    """

    def __init__(self, n_estimators: int = 200, random_state: int = 1337) -> None:
        self.n_estimators = n_estimators
        self.random_state = random_state
        self._scaler = StandardScaler()
        self._model = IsolationForest(
            n_estimators=n_estimators,
            contamination="auto",
            random_state=random_state,
        )
        self._train_mean: float = 0.0
        self._train_std: float = 1.0
        self._fitted = False

    @staticmethod
    def _compress(x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        return np.log1p(np.clip(x, a_min=0, a_max=None))

    def fit(self, x: np.ndarray) -> "LocalIsolationForestDetector":
        xc = self._compress(x)
        xs = self._scaler.fit_transform(xc)
        self._model.fit(xs)
        raw = -self._model.score_samples(xs)
        self._train_mean = float(np.mean(raw))
        self._train_std = float(np.std(raw)) or 1.0
        self._fitted = True
        return self

    def score(self, x: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Detector must be fit before scoring.")
        xs = self._scaler.transform(self._compress(x))
        raw = -self._model.score_samples(xs)
        sigma = (raw - self._train_mean) / self._train_std
        return np.clip(sigma, a_min=0.0, a_max=None)


class SageMakerRandomCutForestDetector(AnomalyDetector):
    """Production detector: Amazon SageMaker Random Cut Forest (batch transform).

    Intentionally not wired for the local portfolio demo - it documents the AWS
    swap target. In production this would: write the baseline feature matrix to
    ``s3://{bucket}/features/training/``, run an RCF training job, then a batch
    transform over ``features/latest.csv`` and read ``scores.csv`` back. boto3
    is imported lazily and only when this backend is explicitly selected.
    """

    def __init__(self, **kwargs: object) -> None:
        self._kwargs = kwargs

    def _unavailable(self) -> RuntimeError:
        return RuntimeError(
            "SageMakerRandomCutForestDetector requires real AWS (SageMaker + S3) "
            "and is not used in the local demo. Run with DETECTOR_BACKEND=local "
            "(default). This class exists to show the production swap target."
        )

    def fit(self, x: np.ndarray) -> "SageMakerRandomCutForestDetector":
        raise self._unavailable()

    def score(self, x: np.ndarray) -> np.ndarray:
        raise self._unavailable()


def build_detector(backend: str, random_state: int = 1337) -> AnomalyDetector:
    """Factory making the SageMaker swap a single config switch."""

    backend = (backend or "local").lower()
    if backend == "local":
        return LocalIsolationForestDetector(random_state=random_state)
    if backend == "sagemaker":
        return SageMakerRandomCutForestDetector(random_state=random_state)
    raise ValueError(f"Unknown DETECTOR_BACKEND: {backend!r}")

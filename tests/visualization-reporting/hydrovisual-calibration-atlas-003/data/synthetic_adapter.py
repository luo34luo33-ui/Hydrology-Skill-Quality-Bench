from __future__ import annotations
import numpy as np
import pandas as pd

class Evaluator:
    def __init__(self, problem): self.problem = problem
    def evaluate(self, parameters, split):
        if split != 'calibration': raise ValueError('search evaluate must use calibration split only')
        loss = (parameters['x'] - 0.25) ** 2 + (parameters['y'] - 0.75) ** 2
        score = 1.0 - loss
        return {'objective': score, 'metrics': {'score': score, 'rmse': loss ** 0.5}}
    def materialize(self, parameters, split):
        loss = (parameters['x'] - 0.25) ** 2 + (parameters['y'] - 0.75) ** 2
        score = 1.0 - loss
        result = {'objective': score, 'metrics': {'score': score, 'rmse': loss ** 0.5}}
        observed = np.linspace(1.0, 2.0, 12)
        shift = (parameters['x'] - 0.25) + (parameters['y'] - 0.75)
        frame = pd.DataFrame({'observed': observed, 'simulated': observed + shift, 'scored': [False, False] + [True] * 10, 'precipitation': np.linspace(0, 5, 12)})
        if self.problem['data_shape'] == 'continuous': frame.insert(0, 'time', pd.date_range('2020-01-01' if split == 'calibration' else '2021-01-01', periods=12, freq='D', tz='UTC'))
        else:
            frame.insert(0, 'event_id', (['C01'] * 6 + ['C02'] * 6) if split == 'calibration' else (['E01'] * 6 + ['E02'] * 6))
            frame.insert(1, 'step', list(range(6)) * 2)
        return {**result, 'series': frame}

def create_evaluator(problem, problem_dir): return Evaluator(problem)

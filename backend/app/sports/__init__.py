"""MedPull Sports: the athlete's app and the team dashboard.

The third variant beside the clinic chart and the personal space. An
athlete's account is a ``Patient`` with ``account_kind="sports"`` (see
``app/personal/scope.py``) and the rows in ``app/models/sports.py``.

Modules:

* ``catalog``      the metric vocabulary: performance tests and their
                   benchmarks, injuries with phases and return-to-sport
                   criteria, wellness keys, the device landscape
* ``identity``     creating an account, joining an organisation
* ``data``         what the boards read, loaded once per request
* ``performance``  the performance board (tests, benchmarks, asymmetry)
* ``recovery``     readiness and recovery (wearable stream + wellness + load)
                   and the recovery suggestions
* ``rehab``        the injury engine: phase placement, criteria, LSI, next focus
* ``plan``         the day's tasks
* ``insights``     the athlete's brief
* ``coach``        the agent
* ``api``          the routes (athlete app and team dashboard)
* ``seed``         the Rice basketball demo roster
"""

# Contributing

CachePilot welcomes reproducible benchmark, policy, and UI improvements. Open an issue before large architecture changes so measurement scope and evidence labels are clear.

1. Fork or branch from `main`; use Python 3.10+ and `python -m pip install -r requirements.txt`.
2. Run `python -m unittest discover -s tests -v` and `python -m cachepilot.replay.generate_demo` before a pull request.
3. Keep V1 benchmark scripts and archived Store CSV/figures intact. Do not replace historical data with a simulated result. Add new results under a clearly named path.
4. Label every reported number as real measurement, model-based estimate, simulation, or replay. State hardware, seed, configuration and workload for comparisons.
5. Keep decision logic outside `dashboard.py`, document new thresholds and add tests for behavior and reproducibility.

Pull requests should summarize behavior, tests, provenance and known limits. Security-sensitive issues should be reported privately to repository maintainers rather than posted with credentials or host details in a public issue.

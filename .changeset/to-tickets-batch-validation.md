---
"mattpocock-skills": patch
---

Add a batch-validation step to `to-tickets` before the user quiz: walk the blocking graph in topological order so each ticket is implementable and independently verifiable from its declared blockers, catch hidden forward dependencies, check source-requirement coverage in both directions, and reject tickets that invent thresholds or internally contradictory constraints.

# DiffMind review bot testbed

This repository contains synthetic code for testing an automated pull-request reviewer.
Deliberately faulty examples belong on labelled test PRs, not on the default branch.
No production data or credentials belong here.

The sample ledger uses integer cents and requires positive amounts. Refunds cannot
exceed the captured payment. Authorization belongs at the service boundary.

Run the sample tests with `python -m unittest discover -s tests_sample`.

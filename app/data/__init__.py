"""Synthetic plant data: CSV seed files (seed_csv/) loaded into SQLite, one
module per domain (production.py, energy.py, emissions.py, water.py,
waste.py, maintenance.py, evidence.py), each implementing the
`PlantDataSource` / `DocumentSource` interface in base.py. Swapping in
SAP/IoT/CEMS/an enterprise ESG database later means a new class per domain
implementing the same interface -- callers never change. Implemented in
Phase 2."""

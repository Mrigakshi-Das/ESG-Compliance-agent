"""Unit tests for app.reports.kpi_dashboard."""

from app.reports.kpi_dashboard import build_kpi_dashboard


class TestBuildKPIDashboard:
    def test_covers_all_esg_domains(self):
        entries = build_kpi_dashboard("Plant A", "FY2025-26 Q4")
        names = {e.name for e in entries}
        assert "Emission Intensity" in names
        assert "Specific Thermal Energy Consumption" in names
        assert "Water Intensity" in names
        assert "Waste Generated" in names
        assert "Renewable Energy Share" in names

    def test_illustrative_target_flagged(self):
        entries = build_kpi_dashboard("Plant B", "FY2025-26 Q4")
        emission = next(e for e in entries if e.name == "Emission Intensity")
        assert emission.target_is_illustrative is True
        assert emission.status == "Exceeds Target"

    def test_no_target_configured_for_untargeted_metric(self):
        entries = build_kpi_dashboard("Plant A", "FY2025-26 Q4")
        waste = next(e for e in entries if e.name == "Waste Generated")
        assert waste.target is None
        assert waste.status == "No Target Configured"

    def test_missing_data_never_fabricates_a_value(self):
        # KNOWN_DATA_ISSUES.md #1: Plant C, FY2025-26 Q3 has no production.
        entries = build_kpi_dashboard("Plant C", "FY2025-26 Q3")
        clinker = next(e for e in entries if e.name == "Clinker Production")
        assert clinker.value is None
        assert clinker.data_status == "missing"
        assert clinker.status == "Data Missing"

    def test_conflicting_data_never_fabricates_a_value(self):
        entries = build_kpi_dashboard("Plant C", "FY2025-26 Q2")
        clinker = next(e for e in entries if e.name == "Clinker Production")
        assert clinker.value is None
        assert clinker.data_status == "conflict"
        assert clinker.status == "Data Conflict"

    def test_plant_a_within_target_on_emission_intensity(self):
        entries = build_kpi_dashboard("Plant A", "FY2025-26 Q4")
        emission = next(e for e in entries if e.name == "Emission Intensity")
        assert emission.status == "Within Target"

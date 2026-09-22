"""Tools: get_historical_metric, compare_plants.

Cross-cutting analytics tools that compose the domain tools + metric
registry (`app.tools.metrics`) rather than reading `app.data` directly, so
they inherit the same missing/conflict handling instead of reimplementing
it. Intended for trend investigation ("why did Plant B's emission intensity
increase?") and cross-plant benchmarking.
"""

from typing import Any, Literal

from app.data.constants import PERIODS, PLANTS
from app.tools._common import validate_period, validate_plant
from app.tools.metrics import METRIC_REGISTRY, fetch_metric_value
from app.tools.schema import ToolParam, ToolSpec

Trend = Literal["increasing", "decreasing", "flat", "insufficient_data"]

_TREND_TOLERANCE_PCT = 2.0  # a change smaller than this is reported as "flat"

GET_HISTORICAL_METRIC_SPEC = ToolSpec(
    name="get_historical_metric",
    description="Return a metric's value across multiple reporting periods for one plant, with a trend classification.",
    inputs=[
        ToolParam("plant", "str", True, "One of the configured plant identifiers."),
        ToolParam("metric", "str", True, f"One of: {sorted(METRIC_REGISTRY)}."),
        ToolParam("periods", "list[str]", False, "Defaults to all configured periods, oldest first."),
    ],
    output_description=(
        "{plant, metric, unit, series: [{period, value, status, issues}], "
        f"trend: 'increasing'|'decreasing'|'flat'|'insufficient_data'}}. Trend compares the "
        f"first and last periods with usable data; a change under {_TREND_TOLERANCE_PCT}% is 'flat', "
        "and fewer than two usable periods gives 'insufficient_data' rather than a guess."
    ),
    raises="ToolInputError if plant/metric/any period is not one of the configured values.",
)

COMPARE_PLANTS_SPEC = ToolSpec(
    name="compare_plants",
    description="Compare a metric's value across plants for one reporting period, ranked best-to-worst.",
    inputs=[
        ToolParam("metric", "str", True, f"One of: {sorted(METRIC_REGISTRY)}."),
        ToolParam("period", "str", True, "A configured fiscal-quarter period."),
        ToolParam("plants", "list[str]", False, "Defaults to all configured plants."),
    ],
    output_description=(
        "{metric, period, unit, direction, results: [{plant, value, status, issues}], "
        "ranked: [plant, ...] (best first, unavailable plants excluded), "
        "unavailable_plants: [plant, ...]}."
    ),
    raises="ToolInputError if metric/period/any plant is not one of the configured values.",
)


def get_historical_metric(plant: str, metric: str, periods: list[str] | None = None) -> dict[str, Any]:
    validate_plant(plant)
    periods = periods if periods is not None else PERIODS
    for p in periods:
        validate_period(p)

    series = []
    unit = ""
    for period in periods:
        mv = fetch_metric_value(plant, period, metric)
        unit = mv.unit
        series.append({"period": period, "value": mv.value, "status": mv.status, "issues": mv.issues})

    ok_values = [(i, s["value"]) for i, s in enumerate(series) if s["status"] == "ok"]
    trend: Trend
    if len(ok_values) < 2:
        trend = "insufficient_data"
    else:
        first_value = ok_values[0][1]
        last_value = ok_values[-1][1]
        if first_value == 0:
            trend = "insufficient_data"
        else:
            pct_change = (last_value - first_value) / abs(first_value) * 100
            if pct_change > _TREND_TOLERANCE_PCT:
                trend = "increasing"
            elif pct_change < -_TREND_TOLERANCE_PCT:
                trend = "decreasing"
            else:
                trend = "flat"

    return {"plant": plant, "metric": metric, "unit": unit, "series": series, "trend": trend}


def compare_plants(metric: str, period: str, plants: list[str] | None = None) -> dict[str, Any]:
    validate_period(period)
    plants = plants if plants is not None else PLANTS
    for p in plants:
        validate_plant(p)

    direction = METRIC_REGISTRY[metric].direction if metric in METRIC_REGISTRY else None
    results = []
    unit = ""
    for plant in plants:
        mv = fetch_metric_value(plant, period, metric)
        unit = mv.unit
        results.append({"plant": plant, "value": mv.value, "status": mv.status, "issues": mv.issues})

    ok_results = [r for r in results if r["status"] == "ok"]
    reverse = direction == "higher_is_better"
    ranked = [r["plant"] for r in sorted(ok_results, key=lambda r: r["value"], reverse=reverse)]
    unavailable = [r["plant"] for r in results if r["status"] != "ok"]

    return {
        "metric": metric,
        "period": period,
        "unit": unit,
        "direction": direction,
        "results": results,
        "ranked": ranked,
        "unavailable_plants": unavailable,
    }

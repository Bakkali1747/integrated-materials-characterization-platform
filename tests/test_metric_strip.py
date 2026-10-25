from gui.widgets.metric_strip import MetricStrip


def test_metric_strip_reads_existing_summary(qtbot):
    strip = MetricStrip()
    qtbot.addWidget(strip)
    summary = {
        "global_minima": [
            {"rl_min_db": -59.64, "frequency_ghz": 5.4, "thickness_mm": 3.69},
            {"rl_min_db": -59.64, "frequency_ghz": 5.5, "thickness_mm": 3.70},
        ],
        "standard_eab": {
            "maximum_bandwidth_ghz": 6.8006,
            "best_thicknesses": [{"thickness_mm": 1.74}],
        },
        "curve_minima": [{"rl_min_db": -23.55}],
        "curve_standard_eab": {"maximum_continuous_bandwidth_ghz": 5.24},
    }
    record = {"configuration": {"curve_thickness_mm": 2.12}}
    strip.update_from_summary(summary, record)
    assert strip.cards[0].value.text() == "-59.64 dB"
    assert "3.69 mm" in strip.cards[0].detail.text()
    assert strip.cards[1].value.text() == "6.80 GHz"
    assert "1.74 mm" in strip.cards[1].detail.text()
    assert strip.cards[2].value.text() == "-23.55 dB"
    assert "2.12 mm" in strip.cards[2].detail.text()
    assert strip.cards[3].value.text() == "5.24 GHz"
    assert not strip.isHidden()

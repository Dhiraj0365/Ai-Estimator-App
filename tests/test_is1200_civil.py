from __future__ import annotations

import math

import pytest

from engines.is1200_civil import IS1200Engine


def test_volume_simple():
    res = IS1200Engine.volume(5.0, 2.0, 0.3)
    assert res["gross"] == pytest.approx(3.0, rel=1e-6)
    assert res["deductions"] == 0.0
    assert res["net"] == pytest.approx(3.0, rel=1e-6)
    assert res["pct"] == 0.0


def test_volume_with_deduction():
    res = IS1200Engine.volume(5.0, 2.0, 0.3, deductions=0.5)
    assert res["gross"] == pytest.approx(3.0, rel=1e-6)
    assert res["deductions"] == pytest.approx(0.5, rel=1e-6)
    assert res["net"] == pytest.approx(2.5, rel=1e-6)
    assert res["pct"] == pytest.approx(0.5 / 3.0 * 100.0, rel=1e-3)


def test_trench_excavation_vertical_sides():
    res = IS1200Engine.trench_excavation(10.0, 1.0, 1.5, side_slope_h_over_v=0.0)
    # gross = 10 * 1 * 1.5 = 15
    assert res["gross"] == pytest.approx(15.0, rel=1e-6)
    assert res["net"] == pytest.approx(15.0, rel=1e-6)


def test_trench_excavation_with_side_slope():
    # bottom breadth = 1.0, depth = 1.5, slope 0.5H:1V
    # top_b = 1 + 2 * 0.5 * 1.5 = 2.5
    # avg_b = (1 + 2.5) / 2 = 1.75
    # gross = 10 * 1.75 * 1.5 = 26.25
    res = IS1200Engine.trench_excavation(10.0, 1.0, 1.5, side_slope_h_over_v=0.5)
    assert res["gross"] == pytest.approx(26.25, rel=1e-6)
    assert res["net"] == pytest.approx(26.25, rel=1e-6)


def test_pit_excavation_vertical():
    res = IS1200Engine.pit_excavation(2.0, 2.0, 1.0, side_slope_h_over_v=0.0)
    # 2 x 2 x 1 = 4
    assert res["gross"] == pytest.approx(4.0, rel=1e-6)
    assert res["net"] == pytest.approx(4.0, rel=1e-6)


def test_pit_excavation_with_side_slope():
    # bottom 2x2, depth 1, slope 0.5:
    # top_L = 2 + 2*0.5*1 = 3
    # top_B = 2 + 2*0.5*1 = 3
    # avg_L = (2+3)/2 = 2.5, avg_B = 2.5
    # gross = 2.5 * 2.5 * 1 = 6.25
    res = IS1200Engine.pit_excavation(2.0, 2.0, 1.0, side_slope_h_over_v=0.5)
    assert res["gross"] == pytest.approx(6.25, rel=1e-6)
    assert res["net"] == pytest.approx(6.25, rel=1e-6)


def test_backfill_with_compaction():
    # base gross = 5 * 2 * 1 = 10; compaction_factor=1.05 -> additions = 0.5
    res = IS1200Engine.backfill(5.0, 2.0, 1.0, compaction_factor=1.05)
    assert res["gross"] == pytest.approx(10.0, rel=1e-6)
    assert res["additions"] == pytest.approx(0.5, rel=1e-6)
    assert res["net"] == pytest.approx(10.5, rel=1e-6)


def test_brickwork_wall_with_opening():
    # Wall 5m long x 3m high x 0.23m thick
    # Gross volume = 5 * 0.23 * 3 = 3.45 m3
    # One opening 1m x 2m => area = 2 > small_opening_limit (0.1)
    # Deduction = 2 * 0.23 = 0.46; net = 3.45 - 0.46 = 2.99
    res = IS1200Engine.brickwork_wall(
        length=5.0,
        thickness=0.23,
        height=3.0,
        openings=[{"w": 1.0, "h": 2.0, "n": 1}],
    )
    assert res["gross"] == pytest.approx(3.45, rel=1e-6)
    assert res["deductions"] == pytest.approx(0.46, rel=1e-6)
    assert res["net"] == pytest.approx(2.99, rel=1e-6)


def test_wall_finish_area_no_openings():
    # L=5, H=3, sides=2 -> gross=5*3*2 = 30
    res = IS1200Engine.wall_finish_area(5.0, 3.0, sides=2, openings=[])
    assert res["gross"] == pytest.approx(30.0, rel=1e-6)
    assert res["deductions"] == 0.0
    assert res["net"] == pytest.approx(30.0, rel=1e-6)


def test_wall_finish_area_small_opening_no_deduction():
    # Opening area = 0.4 sqm <= 0.5 => no deduction
    res = IS1200Engine.wall_finish_area(
        5.0,
        3.0,
        sides=2,
        openings=[{"w": 0.5, "h": 0.8, "n": 1}],
    )
    assert res["gross"] == pytest.approx(30.0, rel=1e-6)
    assert res["deductions"] == pytest.approx(0.0, rel=1e-6)
    assert res["net"] == pytest.approx(30.0, rel=1e-6)


def test_wall_finish_area_medium_opening_one_face_deduction():
    # Opening area = 1.5 sqm (1.5m x 1m) → between 0.5 and 3 sqm
    # Deduct A for ONE face only: deduction = 1.5
    # Gross = 30, net = 28.5
    res = IS1200Engine.wall_finish_area(
        5.0,
        3.0,
        sides=2,
        openings=[{"w": 1.5, "h": 1.0, "n": 1}],
    )
    assert res["gross"] == pytest.approx(30.0, rel=1e-6)
    assert res["deductions"] == pytest.approx(1.5, rel=1e-6)
    assert res["net"] == pytest.approx(28.5, rel=1e-6)


def test_floor_area_with_wastage():
    # L=4, B=3 → base net=12 sqm; wastage_factor=1.03 ⇒ additions=0.36; net=12.36
    res = IS1200Engine.floor_area_with_wastage(4.0, 3.0, wastage_factor=1.03)
    assert res["gross"] == pytest.approx(12.0, rel=1e-6)
    assert res["additions"] == pytest.approx(0.36, rel=1e-6)
    assert res["net"] == pytest.approx(12.36, rel=1e-6)


def test_formwork_column_area():
    # 2*(L+B)*H => 2*(0.3+0.4)*3 = 4.2
    area = IS1200Engine.formwork_column_area(0.3, 0.4, 3.0)
    assert area == pytest.approx(4.2, rel=1e-6)


def test_formwork_beam_area():
    # (2*depth + breadth)*length => (2*0.5 + 0.25)*4 = (1 + 0.25)*4 = 5.0
    area = IS1200Engine.formwork_beam_area(0.25, 0.5, 4.0)
    assert area == pytest.approx(5.0, rel=1e-6)


def test_formwork_slab_area():
    area = IS1200Engine.formwork_slab_area(5.0, 3.0)
    assert area == pytest.approx(15.0, rel=1e-6)


def test_staircase_waist_slab_volume():
    # Waist = 4 * 1.2 * 0.15 = 0.72; landings=0.3 => total 1.02
    res = IS1200Engine.staircase_waist_slab_volume(4.0, 1.2, 0.15, landings_volume=0.3)
    assert res["gross"] == pytest.approx(1.02, rel=1e-6)
    assert res["net"] == pytest.approx(1.02, rel=1e-6)


def test_steel_from_kg_per_cum():
    res = IS1200Engine.steel_from_kg_per_cum(1.5, 120.0)
    assert res["gross"] == pytest.approx(180.0, rel=1e-6)
    assert res["net"] == pytest.approx(180.0, rel=1e-6)


def test_steel_from_bars():
    # dia=12mm, length=6m, count=10; wt/m = d^2/162 = 144/162 ≈ 0.8889
    # total ≈ 0.8889 * 6 * 10 ≈ 53.33 kg
    res = IS1200Engine.steel_from_bars(12.0, 6.0, 10)
    assert res["gross"] == pytest.approx(53.33, rel=1e-2)
    assert res["net"] == pytest.approx(53.33, rel=1e-2)


def test_steel_slab_single_layer():
    # slab 5m x 4m, spacing 150mm => n_bars ≈ floor(4000/150)+1 = 26+1=27
    # each bar 5m, wt/m for 12mm = 144/162 ≈ 0.8889
    # total ≈ 0.8889 * 5 * 27 ≈ 120 kg
    res = IS1200Engine.steel_slab_single_layer(5.0, 4.0, 12.0, 150.0)
    assert res["gross"] == pytest.approx(120.0, rel=1e-2)
    assert res["net"] == pytest.approx(120.0, rel=1e-2)
```

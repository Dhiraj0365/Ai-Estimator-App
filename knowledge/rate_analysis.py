# ---------------------------------------------------------------------
# Sample rate analysis library – keyed by DSR CODE of PARENT item
# YOU MUST ALIGN codes with your actual DSR.
# ---------------------------------------------------------------------

RATE_ANALYSIS_BY_CODE: Dict[str, RateAnalysisEntry] = {

    # -----------------------------------------------------------------
    # RCC – M20, M25 (beams / slabs / columns)
    # -----------------------------------------------------------------

    # RCC M20 in beams, slabs, roofs – per 1 m3
    # CPWD DSR 2023: 5.22.1 (check in your schedule)
    "5.22.1": RateAnalysisEntry(
        code="5.22.1",
        description="RCC work M20 in beams, suspended floors, roofs etc.",
        parent_unit="m3",
        materials=[
            MaterialComponent(  # cement
                qty_per_unit=7.0,         # bags/m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(  # sand
                qty_per_unit=0.44,        # m3/m3 RCC – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
            MaterialComponent(  # aggregate
                qty_per_unit=0.88,        # m3/m3 RCC – example
                item_key="MAT_AGGREGATE_M3",
                display_name="Coarse aggregate",
                unit="m3",
            ),
            MaterialComponent(  # reinforcement
                qty_per_unit=100.0,       # kg/m3 RCC – example
                item_key="STEEL_REINF_FE500",
                display_name="Reinforcement steel (Fe500)",
                unit="kg",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.25),
            LabourComponent("Mazdoor", 0.75),
            LabourComponent("BarBender", 0.20),
        ],
        plant=[
            PlantComponent("ConcreteMixer_0.2m3", 0.30),
            PlantComponent("Vibrator", 0.30),
        ],
        reference="CPWD AoR 2023 – RCC M20; IS 456:2000",
    ),

    # RCC M25 in beams/slabs – per 1 m3 (slightly higher cement & steel)
    # CPWD DSR 2023: e.g. 5.22.2 (verify in your book)
    "5.22.2": RateAnalysisEntry(
        code="5.22.2",
        description="RCC work M25 in beams, suspended floors, roofs etc.",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=8.0,         # bags/m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.44,
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
            MaterialComponent(
                qty_per_unit=0.88,
                item_key="MAT_AGGREGATE_M3",
                display_name="Coarse aggregate",
                unit="m3",
            ),
            MaterialComponent(
                qty_per_unit=115.0,       # kg/m3 – example
                item_key="STEEL_REINF_FE500",
                display_name="Reinforcement steel (Fe500)",
                unit="kg",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.27),
            LabourComponent("Mazdoor", 0.80),
            LabourComponent("BarBender", 0.22),
        ],
        plant=[
            PlantComponent("ConcreteMixer_0.2m3", 0.32),
            PlantComponent("Vibrator", 0.32),
        ],
        reference="CPWD AoR 2023 – RCC M25; IS 456:2000",
    ),

    # -----------------------------------------------------------------
    # PCC – 1:2:4 and 1:4:8 (for flooring, levelling)
    # -----------------------------------------------------------------

    # PCC 1:2:4 – e.g. nominal mix for flooring, per 1 m3
    # Example DSR: 4.1.3 – check your book
    "4.1.3": RateAnalysisEntry(
        code="4.1.3",
        description="Plain cement concrete 1:2:4 (1 cement : 2 sand : 4 aggregate)",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=6.3,         # bags/m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.44,        # m3 sand/m3 PCC – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
            MaterialComponent(
                qty_per_unit=0.88,        # m3 agg/m3 PCC – example
                item_key="MAT_AGGREGATE_M3",
                display_name="Coarse aggregate",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.20),
            LabourComponent("Mazdoor", 0.60),
        ],
        plant=[
            PlantComponent("ConcreteMixer_0.2m3", 0.25),
            PlantComponent("Vibrator", 0.20),
        ],
        reference="CPWD AoR 2023 – PCC 1:2:4",
    ),

    # PCC 1:4:8 – lean concrete, per 1 m3
    # Example DSR: 4.1.5 – check your book
    "4.1.5": RateAnalysisEntry(
        code="4.1.5",
        description="Plain cement concrete 1:4:8 (1 cement : 4 sand : 8 aggregate)",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=4.0,         # bags/m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.57,        # m3 sand/m3 PCC – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
            MaterialComponent(
                qty_per_unit=0.86,        # m3 agg/m3 PCC – example
                item_key="MAT_AGGREGATE_M3",
                display_name="Coarse aggregate",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.15),
            LabourComponent("Mazdoor", 0.50),
        ],
        plant=[
            PlantComponent("ConcreteMixer_0.2m3", 0.20),
        ],
        reference="CPWD AoR 2023 – PCC 1:4:8",
    ),

    # -----------------------------------------------------------------
    # Brickwork – 230 mm and 115 mm
    # -----------------------------------------------------------------

    # Brickwork 230mm, superstructure, 1:6, per 1 m3
    # CPWD DSR 2023: 6.4.2
    "6.4.2": RateAnalysisEntry(
        code="6.4.2",
        description="Brick work in superstructure in cement mortar 1:6, 230mm thick",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=500.0,         # bricks/m3 – example
                item_key="MAT_BRICK_FPS",
                display_name="Bricks (FPS)",
                unit="nos",
            ),
            MaterialComponent(
                qty_per_unit=1.0,           # bags/m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.24,          # m3/m3 brickwork – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.35),
            LabourComponent("Mazdoor", 1.00),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Brickwork; IS 2212",
    ),

    # Brick partition 115mm, 1:4, per 1 m3
    # Example DSR: check your code (e.g. 6.1.x)
    "6.1.1": RateAnalysisEntry(
        code="6.1.1",
        description="Half-brick partition wall 115mm thick in cement mortar 1:4",
        parent_unit="m3",
        materials=[
            MaterialComponent(
                qty_per_unit=520.0,         # bricks/m3 – example
                item_key="MAT_BRICK_FPS",
                display_name="Bricks (FPS)",
                unit="nos",
            ),
            MaterialComponent(
                qty_per_unit=1.2,           # bags/m3 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.25,          # m3/m3 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.40),
            LabourComponent("Mazdoor", 1.10),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Half-brick wall; IS 2212",
    ),

    # -----------------------------------------------------------------
    # Plaster – 12mm 1:6, 6mm 1:3
    # -----------------------------------------------------------------

    # 12 mm plaster 1:6, per 1 m2
    # CPWD DSR 2023: 13.4.1
    "13.4.1": RateAnalysisEntry(
        code="13.4.1",
        description="12mm cement plaster in 1:6 on brick/RCC, single coat",
        parent_unit="m2",
        materials=[
            MaterialComponent(
                qty_per_unit=0.09,          # bag/m2 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.003,         # m3/m2 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.10),
            LabourComponent("Mazdoor", 0.20),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Plaster; IS 1661",
    ),

    # 6mm plaster 1:3, per 1 m2
    # Example DSR: 13.11.1 (check your book)
    "13.11.1": RateAnalysisEntry(
        code="13.11.1",
        description="6mm cement plaster in 1:3 on concrete surfaces",
        parent_unit="m2",
        materials=[
            MaterialComponent(
                qty_per_unit=0.05,          # bag/m2 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.0017,        # m3/m2 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.08),
            LabourComponent("Mazdoor", 0.15),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Plaster (thin); IS 1661",
    ),

    # -----------------------------------------------------------------
    # Tiles – vitrified floor, ceramic wall
    # -----------------------------------------------------------------

    # Vitrified floor tiles 600x600 – per 1 m2
    # CPWD DSR 2023: 11.41.2 (verify)
    "11.41.2": RateAnalysisEntry(
        code="11.41.2",
        description="Vitrified floor tiles in cement mortar, 600×600mm",
        parent_unit="m2",
        materials=[
            MaterialComponent(
                qty_per_unit=1.05,          # including 5% wastage
                item_key="MAT_TILE_VITRIFIED_M2",
                display_name="Vitrified tiles",
                unit="m2",
            ),
            MaterialComponent(
                qty_per_unit=0.08,          # bag/m2 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.002,         # m3/m2 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.12),
            LabourComponent("Mazdoor", 0.18),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Flooring; IS 1443",
    ),

    # Ceramic wall tiles 300x450, per 1 m2
    # Example DSR: 11.36.1 (check your book)
    "11.36.1": RateAnalysisEntry(
        code="11.36.1",
        description="Ceramic glazed wall tiles, 300×450mm, on 12mm plaster bed",
        parent_unit="m2",
        materials=[
            MaterialComponent(
                qty_per_unit=1.05,          # m2 tiles per m2 area
                item_key="MAT_TILE_VITRIFIED_M2",  # or separate MAT_TILE_CERAMIC
                display_name="Ceramic wall tiles",
                unit="m2",
            ),
            MaterialComponent(
                qty_per_unit=0.06,          # bag/m2 – example
                item_key="MAT_CEMENT_BAG",
                display_name="Cement (bags)",
                unit="bag",
            ),
            MaterialComponent(
                qty_per_unit=0.0015,        # m3/m2 – example
                item_key="MAT_SAND_M3",
                display_name="Sand",
                unit="m3",
            ),
        ],
        labour=[
            LabourComponent("Mason", 0.14),
            LabourComponent("Mazdoor", 0.20),
        ],
        plant=[],
        reference="CPWD AoR 2023 – Wall tiling; IS 1443",
    ),
}

RA_CODES = set(RATE_ANALYSIS_BY_CODE.keys())

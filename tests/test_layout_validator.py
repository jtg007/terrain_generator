from src.terrain_spec import TerrainSpec
from src.layout_validator import LayoutValidator

def create_minimal_spec(size: int = 2048) -> TerrainSpec:
    return TerrainSpec(
        origin_x=0,
        origin_y=0,
        size_x=size,
        size_y=size,
        cell_size=512,
        base_clear_radius=512,
        displacement_power=3,
    )

def test_valid_layout():
    # 4x4 tiles (2048x2048)
    spec = create_minimal_spec(2048)
    # Use valid positions, far apart
    imp_base = (512, 512)
    nf_base = (1536, 1536)
    # resource in corner
    resources = [(1536, 512)]

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is True
    assert len(result.errors) == 0
    assert len(result.invalid_entities) == 0

def test_bases_too_close():
    spec = create_minimal_spec(2048)
    imp_base = (1024, 1024)
    nf_base = (1024, 1100) # Distance is 76. Min required is 0.40 * 2048 = 819.2
    resources = []

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is False
    assert "Bases are too close to each other" in result.errors[0]
    assert "imp" in result.invalid_entities
    assert "nf" in result.invalid_entities

def test_base_out_of_bounds():
    spec = create_minimal_spec(2048)
    # Imp base margin is 512, placing at x=200 is out of bounds
    imp_base = (200, 1024)
    nf_base = (1536, 1536)
    resources = []

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is False
    assert any("out of bounds" in e and "Imp Base" in e for e in result.errors)
    assert "imp" in result.invalid_entities
    assert "nf" not in result.invalid_entities

def test_resource_out_of_bounds():
    spec = create_minimal_spec(2048)
    imp_base = (512, 512)
    nf_base = (1536, 1536)
    # Resource margin is 256, placing at x=100 is out of bounds
    resources = [(100, 1024)]

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is False
    assert any("out of bounds" in e and "Resource 0" in e for e in result.errors)
    assert "0" in result.invalid_entities

def test_resource_inside_base_flatten_radius():
    spec = create_minimal_spec(2048)
    imp_base = (512, 512)
    nf_base = (1536, 1536)

    # Base clear radius is 512.
    # Min dist = 0.15 * 2048 + 512 = 307.2 + 512 = 819.2
    # Place at distance 600 from imp_base (too close)
    resources = [(512, 1112)] # dist = 600

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is False
    assert any("Resource 0 is too close to Imp Base" in e for e in result.errors)
    assert "0" in result.invalid_entities
    assert "imp" in result.invalid_entities

def test_resources_clustered():
    spec = create_minimal_spec(2048)
    imp_base = (512, 512)
    nf_base = (1536, 1536)

    # Res-Res min dist = 0.10 * 2048 = 204.8
    # Place resources with dist = 100
    resources = [(1024, 1536), (1024, 1636)]

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is False
    assert any("too close to each other" in e for e in result.errors)
    assert "0" in result.invalid_entities
    assert "1" in result.invalid_entities

def test_small_map_valid():
    # Using size 4096.
    # Min base dist = 0.4 * 4096 = 1638.4
    # Res to Base min dist = 0.15 * 4096 + 512 = 614.4 + 512 = 1126.4
    spec = create_minimal_spec(4096)
    imp_base = (1024, 1024)
    nf_base = (3072, 3072)

    # Place resource at distance > 1126.4 from imp_base (1024, 1024)
    # (2048, 2048) dist from imp_base = sqrt(1024^2 + 1024^2) = 1448 (Valid)
    resources = [(2048, 2048)]

    validator = LayoutValidator()
    result = validator.validate(spec, imp_base, nf_base, resources)

    assert result.valid is True

def test_fallback_to_defaults():
    # Test spec.validate_layout() behavior
    spec = create_minimal_spec(8192) # 16x16 map

    # Base margin = 512. Default bases are at 0.25 and 0.75 -> 2048, 2048 and 6144, 6144 (valid)
    # Base to Base min dist = 0.4 * 8192 = 3276.8
    # Default bases dist = sqrt(4096^2 + 4096^2) = 5792.6 (valid)

    result = spec.validate_layout()
    assert result.valid is True
    assert len(result.errors) == 0

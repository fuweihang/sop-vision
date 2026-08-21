from algorithm.demos.viewer.geometry import (
    fit_content_rect,
    map_normalized_bbox,
    map_normalized_polygon,
)


def test_fit_content_rect_adds_horizontal_letterbox() -> None:
    content = fit_content_rect(1000, 1000, 1920, 1080)

    assert content.x == 0
    assert content.y == 218.75
    assert content.width == 1000
    assert content.height == 562.5


def test_fit_content_rect_adds_vertical_letterbox() -> None:
    content = fit_content_rect(1200, 600, 600, 800)

    assert content.x == 375
    assert content.y == 0
    assert content.width == 450
    assert content.height == 600


def test_bbox_maps_into_content_rect_and_clips_coordinates() -> None:
    content = fit_content_rect(1000, 1000, 1920, 1080)

    mapped = map_normalized_bbox((-0.2, 0.25, 1.2, 0.75), content)

    assert mapped == (0, 359.375, 1000, 640.625)


def test_polygon_maps_into_letterboxed_content_and_clips_coordinates() -> None:
    content = fit_content_rect(1000, 1000, 1920, 1080)

    mapped = map_normalized_polygon(
        ((-0.1, 0.2), (0.8, 0.2), (1.1, 0.8)),
        content,
    )

    assert mapped == (
        (0, 331.25),
        (800, 331.25),
        (1000, 668.75),
    )

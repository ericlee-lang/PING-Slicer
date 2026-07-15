#include <catch2/catch_all.hpp>

#include "libslic3r/GCode/PingColorMix.hpp"

using namespace Slic3r::PingMix;

TEST_CASE("Photo-tile part names retain recipe and preview color", "[PingColorMix][PhotoTile]")
{
    std::string value;

    REQUIRE(parse_photo_part_name("零件色2 #7f7f7f S0.5", value));
    REQUIRE(value == "M6051 S0.5");
    REQUIRE(parse_photo_part_color("零件色2 #7f7f7f S0.5", value));
    REQUIRE(value == "#7F7F7F");

    REQUIRE(parse_photo_part_name("零件色3 #c07055 A70 B30 C0 D0", value));
    REQUIRE(value == "M6052 A70 B30 C0 D0");
    REQUIRE(parse_photo_part_color("零件色3 #c07055 A70 B30 C0 D0", value));
    REQUIRE(value == "#C07055");
}

TEST_CASE("Legacy dual photo-tile recipes get neutral diagnostic colors", "[PingColorMix][PhotoTile]")
{
    std::string color;
    REQUIRE(parse_photo_part_color("黑色條紋 S0", color));
    REQUIRE(color == "#000000");
    REQUIRE(parse_photo_part_color("灰色條紋 S0.5", color));
    REQUIRE(color == "#808080");
    REQUIRE(parse_photo_part_color("白色條紋 S1", color));
    REQUIRE(color == "#FFFFFF");

    REQUIRE_FALSE(parse_photo_part_color("舊四料 A25 B25 C25 D25", color));
}

TEST_CASE("Photo-tile palette requires complete contiguous assignments", "[PingColorMix][PhotoTile]")
{
    PhotoPalette palette;
    std::string  reason;

    SECTION("valid three-level stripe palette") {
        const std::vector<PhotoPartAssignment> parts = {
            {0, "黑色條紋 #000000 S0"},
            {1, "灰色條紋 #808080 S0.5"},
            {2, "白色條紋 #FFFFFF S1"},
        };
        REQUIRE(collect_photo_palette(parts, palette, reason) == PhotoPaletteStatus::Valid);
        REQUIRE(palette.recipes.size() == 3);
        REQUIRE((palette.colors == std::vector<std::string>{"#000000", "#808080", "#FFFFFF"}));
        REQUIRE(reason.empty());
    }

    SECTION("one part without a recipe is reported as invalid") {
        const std::vector<PhotoPartAssignment> parts = {
            {0, "黑色條紋 #000000 S0"},
            {1, "未指派條紋"},
            {2, "白色條紋 #FFFFFF S1"},
        };
        REQUIRE(collect_photo_palette(parts, palette, reason) == PhotoPaletteStatus::Invalid);
        REQUIRE(reason.find("1 of 3") != std::string::npos);
        REQUIRE(reason.find("未指派條紋") != std::string::npos);
    }

    SECTION("a missing middle slot is reported as invalid") {
        const std::vector<PhotoPartAssignment> parts = {
            {0, "黑色條紋 #000000 S0"},
            {2, "白色條紋 #FFFFFF S1"},
        };
        REQUIRE(collect_photo_palette(parts, palette, reason) == PhotoPaletteStatus::Invalid);
        REQUIRE(reason.find("T1 is missing") != std::string::npos);
    }

    SECTION("a recipe-bearing part without an explicit material is reported as invalid") {
        const std::vector<PhotoPartAssignment> parts = {
            {0, "黑色條紋 #000000 S0"},
            {-1, "灰色條紋 #808080 S0.5"},
            {2, "白色條紋 #FFFFFF S1"},
        };
        REQUIRE(collect_photo_palette(parts, palette, reason) == PhotoPaletteStatus::Invalid);
        REQUIRE(reason.find("no material assignment") != std::string::npos);
    }

    SECTION("ordinary models are ignored") {
        const std::vector<PhotoPartAssignment> parts = {{0, "body"}, {1, "frame"}};
        REQUIRE(collect_photo_palette(parts, palette, reason) == PhotoPaletteStatus::NotPhotoTile);
        REQUIRE(palette.recipes.empty());
    }
}

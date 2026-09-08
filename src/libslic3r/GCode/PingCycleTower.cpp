// PING 照片磚「每層循環洗料塔」——幾何與每層計畫。說明見 PingCycleTower.hpp 檔頭。
#include "PingCycleTower.hpp"
#include "PingColorMix.hpp"
#include "../Print.hpp"
#include "../Model.hpp"
#include "../ClipperUtils.hpp"
#include "../Flow.hpp"
#include "../Exception.hpp"
#include <boost/log/trivial.hpp>
#include <boost/algorithm/string.hpp>
#include <algorithm>
#include <cmath>
#include <sstream>

namespace Slic3r {
namespace PingCycle {

static const std::vector<std::string>& channels_for(const std::string& mode)
{
    static const std::vector<std::string> dual = {"E1", "E0"};
    static const std::vector<std::string> quad = {"E3", "E2", "E1", "E0"};
    static const std::vector<std::string> none;
    return mode == "dual" ? dual : mode == "quad" ? quad : none;
}

const char* pure_recipe(const std::string& mode, const std::string& channel)
{
    if (mode == "dual") {
        if (channel == "E0") return "M6051 S1";
        if (channel == "E1") return "M6051 S0";
    } else if (mode == "quad") {
        if (channel == "E0") return "M6052 A100 B0 C0 D0";
        if (channel == "E1") return "M6052 A0 B100 C0 D0";
        if (channel == "E2") return "M6052 A0 B0 C100 D0";
        if (channel == "E3") return "M6052 A0 B0 C0 D100";
    }
    return "";
}

static bool read_param(const std::string& cmd, char key, double& out)
{
    std::istringstream ss(cmd);
    std::string tok;
    while (ss >> tok) {
        if (tok.size() > 1 && tok[0] == key) {
            try { out = std::stod(tok.substr(1)); return true; } catch (...) { return false; }
        }
        if (tok[0] == ';') break;
    }
    return false;
}

bool is_pure_light_recipe(const std::string& cmd)
{
    if (boost::starts_with(cmd, "M6051")) {
        double s = -1.;
        return read_param(cmd, 'S', s) && std::fabs(s - 1.0) < 1e-6;
    }
    if (boost::starts_with(cmd, "M6052")) {
        double a = -1., b = -1., c = -1., d = -1.;
        if (!read_param(cmd, 'A', a) || !read_param(cmd, 'B', b) || !read_param(cmd, 'C', c) || !read_param(cmd, 'D', d))
            return false;
        return std::fabs(a - 100.) < 1e-6 && std::fabs(b) < 1e-6 && std::fabs(c) < 1e-6 && std::fabs(d) < 1e-6;
    }
    return false;
}

double light_score(const std::string& cmd)
{
    if (boost::starts_with(cmd, "M6051")) {
        double s = -1.;
        return read_param(cmd, 'S', s) ? s : -1.;
    }
    if (boost::starts_with(cmd, "M6052")) {
        double a = -1., b = -1., c = -1., d = -1.;
        if (!read_param(cmd, 'A', a) || !read_param(cmd, 'B', b) || !read_param(cmd, 'C', c) || !read_param(cmd, 'D', d))
            return -1.;
        // 純 A100 → 1.0、純 D100 → 0.0，與 is_pure_light_recipe 的判定相容。
        return (a * 3. + b * 2. + c * 1. + d * 0.) / 300.;
    }
    return -1.;
}

bool enabled_for(const Print& print)
{
    for (const PrintObject* obj : print.objects())
        if (obj->config().ping_pt_cycle.value)
            return true;
    return false;
}

bool collect_palette(const Model& model, std::map<int, std::string>& palette, std::string& reason)
{
    std::vector<PingMix::PhotoPartAssignment> parts;
    for (const ModelObject* obj : model.objects) {
        for (const ModelVolume* vol : obj->volumes) {
            if (!vol->is_model_part()) continue;
            const ConfigOption* extruder = vol->config.option("extruder");
            if ((extruder == nullptr || extruder->getInt() == 0) && vol->get_object() != nullptr)
                extruder = vol->get_object()->config.option("extruder");
            const int explicit_tool = extruder != nullptr && extruder->getInt() > 0 ? extruder->getInt() - 1 : -1;
            parts.push_back({explicit_tool, vol->name});
        }
    }
    PingMix::PhotoPalette parsed;
    const auto status = PingMix::collect_photo_palette(parts, parsed, reason);
    if (status != PingMix::PhotoPaletteStatus::Valid) {
        if (reason.empty()) reason = "not a photo-tile plate";
        palette.clear();
        return false;
    }
    palette = parsed.recipes;
    return true;
}

static std::vector<int> parse_laps(const std::string& s)
{
    std::vector<int> out;
    std::vector<std::string> toks;
    boost::split(toks, s, boost::is_any_of(",; "), boost::token_compress_on);
    for (auto& t : toks) {
        if (t.empty()) continue;
        try { out.push_back(std::stoi(t)); } catch (...) { return {}; }
    }
    return out;
}

std::unique_ptr<Tower> create(const Print& print, std::string& why)
{
    const PrintObject* owner = nullptr;
    for (const PrintObject* obj : print.objects())
        if (obj->config().ping_pt_cycle.value) { owner = obj; break; }
    if (owner == nullptr) { why = "no object enables ping_pt_cycle"; return nullptr; }
    if (print.config().print_sequence == PrintSequence::ByObject) { why = "print_sequence=by object is not supported by the cycle tower"; return nullptr; }

    Settings st;
    st.enabled = true;
    st.mode    = owner->config().ping_pt_cycle_mode.value;
    st.laps    = parse_laps(owner->config().ping_pt_cycle_laps.value);
    st.size_mm = (float) owner->config().ping_pt_cycle_size.value;
    st.gap_mm  = (float) owner->config().ping_pt_cycle_gap.value;
    st.brim_mm = (float) owner->config().ping_pt_cycle_brim.value;
    const auto& chans = channels_for(st.mode);
    if (chans.empty()) { why = "ping_pt_cycle_mode must be dual or quad, got '" + st.mode + "'"; return nullptr; }
    if (st.laps.size() != chans.size()) { why = "ping_pt_cycle_laps needs " + std::to_string(chans.size()) + " entries for " + st.mode; return nullptr; }
    for (int l : st.laps) if (l < 1) { why = "every lap count must be >= 1"; return nullptr; }

    std::map<int, std::string> palette;
    if (!collect_palette(print.model(), palette, why)) return nullptr;

    const float nozzle = (float) print.config().nozzle_diameter.get_at(0);
    // 沒帶尺寸時的預設＝25 mm 固定（Eric 2026-09-08「固定 25」）。原式 44×口徑/0.4 的用意是怕大口徑讓塔內路徑斷掉，
    // 但 照片磚_循環洗料塔/size_sweep.py 實算：路徑連續的最小邊長 0.4／0.6＝8.5 mm、1.0＝12.5 mm ⇒ 25 mm 對全口徑都有兩倍餘裕，
    // 且 25 mm 可容 0.4 25 圈／0.6 18 圈／1.0 10 圈（現行 3～5 圈）。等比放大真正的代價是佔床：0.6 變 66 mm ⇒ 100 mm 磚在
    // FD300（Ø300）上，塔含 brim 的最遠角算出來是半徑 152.9 mm、超過床的 150；固定 25 mm 降到 108.3 mm。
    // 真的放不下或圈數過多時，geometry_for() 仍會把「圈斷裂／空腔封閉」報成 SlicingError，不會默默印出爛塔。
    const float size   = st.size_mm > 0.f ? st.size_mm : 25.f;

    // 塔位置：所有物件包絡的 +X 側、Y 置中；與模型外緣距 gap（brim 另加）
    BoundingBox bb;
    for (const PrintObject* obj : print.objects())
        for (const PrintInstance& inst : obj->instances()) {
            BoundingBox b = obj->bounding_box();
            b.translate(inst.shift);
            bb.merge(b);
        }
    if (!bb.defined) { why = "no printable instance"; return nullptr; }
    const Point center(coord_t(bb.max.x() + scale_(st.gap_mm + st.brim_mm + size / 2.f)), coord_t((bb.min.y() + bb.max.y()) / 2));

    // 列印範圍檢查（塔身＋brim 都要在床內）
    BoundingBoxf bed;
    for (const Vec2d& p : print.config().printable_area.values) bed.merge(p);
    const double half = size / 2. + st.brim_mm;
    const Vec2d c_mm(unscale<double>(center.x()), unscale<double>(center.y()));
    if (bed.defined && (c_mm.x() - half < bed.min.x() || c_mm.x() + half > bed.max.x() || c_mm.y() - half < bed.min.y() || c_mm.y() + half > bed.max.y())) {
        std::ostringstream os;
        os << "PING photo-tile cycle tower does not fit on the bed: tower center (" << c_mm.x() << "," << c_mm.y() << ") size " << size
           << " mm + brim " << st.brim_mm << " mm; bed x " << bed.min.x() << ".." << bed.max.x() << " y " << bed.min.y() << ".." << bed.max.y();
        why = os.str();
        return nullptr;
    }

    auto tower = std::make_unique<Tower>(st, palette, nozzle, center, size, 0.f);
    BOOST_LOG_TRIVIAL(info) << "PING photo-tile cycle tower: mode=" << st.mode << " laps=" << owner->config().ping_pt_cycle_laps.value
                            << " size=" << size << " center=(" << c_mm.x() << "," << c_mm.y() << ") palette=" << palette.size()
                            << " pure-E0 tools=" << tower->pure_light_tools().size();
    return tower;
}

Tower::Tower(Settings s, std::map<int, std::string> palette, float nozzle, Point center, float size, float)
    : m_settings(std::move(s)), m_palette(std::move(palette)), m_nozzle(nozzle), m_size(size), m_center(center)
{
    const auto& chans = channels_for(m_settings.mode);
    int lap = 1;
    for (size_t i = 0; i < chans.size(); ++i) {
        Stage st;
        st.channel    = chans[i];
        st.recipe_cmd = pure_recipe(m_settings.mode, chans[i]);
        st.first_lap  = lap;
        st.last_lap   = lap + m_settings.laps[i] - 1;
        lap           = st.last_lap + 1;
        m_stages.push_back(st);
    }
    for (const auto& kv : m_palette)
        if (is_pure_light_recipe(kv.second))
            m_pure_light_tools.push_back((unsigned int) kv.first);
    build_outline();
}

// jtRound 的第 4 參數在 ClipperUtils 裡是 ArcTolerance（scaled 單位）；不給＝DefaultMiterLimit 3 ＝ 3e-6 mm ⇒ 每圈五千點、
// 塔段一層 5 萬行 G-code（0908 真切 422 MB 實測）。0.02 mm 已遠細於噴嘴，圈點數降一到兩個數量級。
static constexpr double kArcTolMm  = 0.02;
static constexpr double kSimplifyMm = 0.01;   // 圈路徑再走一次 Douglas-Peucker（同 Orca 預設 resolution 量級）
static inline double arc_tol() { return scale_(kArcTolMm); }

static Polygon circle_polygon(const Point& c, double r_scaled, int n = 64)
{
    Polygon p;
    for (int i = 0; i < n; ++i) {
        const double a = 2. * M_PI * i / n;
        p.points.emplace_back(c.x() + coord_t(r_scaled * std::cos(a)), c.y() + coord_t(r_scaled * std::sin(a)));
    }
    return p;
}

static Polygon largest(const Polygons& polys)
{
    Polygon best;
    double  best_area = -1.;
    for (const Polygon& p : polys) {
        const double a = std::fabs(p.area());
        if (a > best_area) { best_area = a; best = p; }
    }
    return best;
}

void Tower::build_outline()
{
    // 與離線版 tower_geometry.py 同一套：圓角方 − 四側大圓（矢高）→ 開運算圓化交接。參數隨塔尺寸等比（44 mm 為基準）。
    const double k        = m_size / 44.;
    const double a        = m_size / 2.;
    const double corner_r = 6. * k, concave_s = 5. * k, smooth = 2. * k;
    Polygon square;
    square.points = { Point(coord_t(scale_(-a)), coord_t(scale_(-a))), Point(coord_t(scale_(a)), coord_t(scale_(-a))), Point(coord_t(scale_(a)), coord_t(scale_(a))), Point(coord_t(scale_(-a)), coord_t(scale_(a))) };
    Polygons rounded = offset(offset(square, -scale_(corner_r), ClipperLib::jtRound, arc_tol()), scale_(corner_r), ClipperLib::jtRound, arc_tol());
    const double c = a - corner_r - 1. * k;
    const double R = (c * c + concave_s * concave_s) / (2. * concave_s);
    const double d = a + R - concave_s;
    Polygons circles;
    for (const Vec2d& cc : { Vec2d(0, d), Vec2d(0, -d), Vec2d(d, 0), Vec2d(-d, 0) })
        circles.push_back(circle_polygon(Point(coord_t(scale_(cc.x())), coord_t(scale_(cc.y()))), scale_(R)));
    Polygons cut = diff(rounded, circles);
    Polygon  outline = largest(offset(offset(largest(cut), -scale_(smooth), ClipperLib::jtRound, arc_tol()), scale_(smooth), ClipperLib::jtRound, arc_tol()));
    outline.make_counter_clockwise();
    outline.translate(m_center);
    m_outline = outline;
}

static Polyline ring_from_seam(Polygon poly, const Point& anchor)
{
    poly.make_counter_clockwise();
    size_t best = 0; double bd = std::numeric_limits<double>::max();
    for (size_t i = 0; i < poly.points.size(); ++i) {
        const double dd = (poly.points[i] - anchor).cast<double>().squaredNorm();
        if (dd < bd) { bd = dd; best = i; }
    }
    return poly.split_at_index((int) best);   // 從接縫頂點起繞一周回到同一點（閉合）
}

const LayerGeometry& Tower::geometry_for(float layer_height, bool first_layer)
{
    const int key = int(std::lround(layer_height * 1000.f)) * 2 + (first_layer ? 1 : 0);
    auto it = m_cache.find(key);
    if (it != m_cache.end()) return it->second;

    LayerGeometry g;
    g.layer_height = layer_height;
    g.width        = m_nozzle;                       // 照片磚製程線寬＝口徑
    Flow flow(g.width, layer_height, m_nozzle);
    g.spacing     = flow.spacing();
    g.mm3_per_mm  = flow.mm3_per_mm();
    const Point anchor(coord_t(m_center.x() - scale_(m_size)), coord_t(m_center.y()));   // 接縫朝 −X（模型側）
    const int   n = m_settings.total_laps();
    for (int i = 0; i < n; ++i) {
        const double inset = g.width / 2. + i * g.spacing;
        Polygons rings = offset(m_outline, -scale_(inset), ClipperLib::jtRound, arc_tol());
        if (rings.empty()) { g.problem = "ring at inset " + std::to_string(inset) + " mm vanishes"; break; }
        if (rings.size() != 1) { g.problem = "ring at inset " + std::to_string(inset) + " mm splits into " + std::to_string(rings.size()) + " rings"; break; }
        g.loops.push_back(ring_from_seam(rings.front(), anchor));
        g.loops.back().simplify(scale_(kSimplifyMm));
    }
    // 🔴 圈序反轉＝loops[0] 變成**最內圈**（Eric 2026-09-09：「由內先畫深色、最外部為淺色，不會在垂直方向看到顏色變化」）。
    // 上面是照 inset 由小到大生的（＝由外往內）；反轉之後，第 1 段（最深）落在最內圈、最後一段（純 E0 最淺）落在最外圈。
    // 列印順序完全沒變，仍是「深→淺」——只是現在等於由內往外走 ⇒ 塔的外皮永遠是最淺的那一路，垂直方向看不到顏色變化。
    // 附帶好處：離塔時人在最外圈，不必再橫越已印的圈。
    std::reverse(g.loops.begin(), g.loops.end());
    if (g.problem.empty()) {
        Polygons cavity = offset(m_outline, -scale_(g.width / 2. + (n - 1) * g.spacing + g.width / 2.), ClipperLib::jtRound, arc_tol());
        if (cavity.size() != 1) g.problem = "central cavity is closed or split";
    }
    if (g.problem.empty() && first_layer && m_settings.brim_mm > 0.f) {
        const int nb = (int) std::ceil(m_settings.brim_mm / g.spacing);
        for (int k = 1; k <= nb; ++k) {                  // 由內往外：接在**最後一段（最淺）的最外圈**之後繼續往外長
            Polygons rings = offset(m_outline, scale_(g.width / 2. + (k - 1) * g.spacing), ClipperLib::jtRound, arc_tol());
            if (rings.size() != 1) { g.problem = "brim ring " + std::to_string(k) + " is not a single ring"; break; }
            g.brim_loops.push_back(ring_from_seam(rings.front(), anchor));
            g.brim_loops.back().simplify(scale_(kSimplifyMm));
        }
    }
    if (!g.problem.empty())
        BOOST_LOG_TRIVIAL(error) << "PING photo-tile cycle tower geometry invalid at layer height " << layer_height << ": " << g.problem;
    return m_cache.emplace(key, std::move(g)).first->second;
}

} // namespace PingCycle
} // namespace Slic3r

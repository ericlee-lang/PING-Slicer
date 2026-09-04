#ifndef slic3r_Format_STEP_hpp_
#define slic3r_Format_STEP_hpp_
#include "XCAFDoc_DocumentTool.hxx"
#include "XCAFApp_Application.hxx"
#include "XCAFDoc_ShapeTool.hxx"
#include <boost/filesystem/path.hpp>
#include <boost/filesystem.hpp>
#include <Message_ProgressIndicator.hxx>
#include <atomic>

namespace fs = boost::filesystem;

namespace Slic3r {

class TriangleMesh;
class ModelObject;

// load step stage
const int LOAD_STEP_STAGE_READ_FILE          = 0;
const int LOAD_STEP_STAGE_GET_SOLID          = 1;
const int LOAD_STEP_STAGE_GET_MESH           = 2;
const int LOAD_STEP_STAGE_NUM                = 3;
const int LOAD_STEP_STAGE_UNIT_NUM           = 5;

typedef std::function<void(int load_stage, int current, int total, bool& cancel)> ImportStepProgressFn;
typedef std::function<void(bool isUtf8)> StepIsUtf8Fn;

struct NamedSolid
{
    NamedSolid(const TopoDS_Shape& s,
               const std::string& n) : solid{ s }, name{ n } {
    }
    const TopoDS_Shape solid;
    const std::string  name;
    int tri_face_cout = 0;
};

/* 【2026-08-24】匯入前哨的判定材料：在「還沒網格化」的時候就能算出來的 BRep 普查。
   刻意只放計數、不放幾何 —— 這一層回答的是「這個檔破了沒」，
   「破在哪裡」需要座標，那是 VibeCAD Repair Core 1.1.0 的事（見契約 §1）。 */
struct StepBRepCensus
{
    /* 【2026-09-04・牌 c-0904-STEP-01】普查到底跑過了沒。
       原本拿 components > 0 當「有跑過」的代理，但那把兩件事混成一件：
       ①普查根本沒跑（m_shape_tool 為空）②普查跑了、而檔案裡真的一個形狀都沒有。
       ②就是 null shape 檔 —— 前哨因此整個沉默，使用者要等到網格化跑完，
       才會看到一句泛用的「檔案是空的」，而且那時候時間已經花掉了。
       分開之後：①維持沉默（不知道就不要亂講）、②照樣示警。 */
    bool inspected = false;

    int components = 0;   // 頂層形狀展開後的總數
    int solids     = 0;   // 其中是封閉實體的
    int shells     = 0;   // 其中只有外殼的

    // 嚴格觸發（Eric 2026-08-24 裁）：整份檔一個實體都沒有，才算「沒有實心結構」。
    // 「有實體也有殼」的混合檔不提示 —— 那是正常設計，誤報一次就會讓提示變雜訊。
    bool has_no_solid() const { return inspected && solids == 0; }

    // 連殼都沒有 —— null shape／空檔。文案必須跟「只有殼」分開講，
    // 否則會吐出「裡面的 0 個組件全部只有外殼」這種不通的句子。
    bool has_no_geometry() const { return inspected && components == 0; }
};

//BBS: Load an step file into a provided model.
extern bool load_step(const char *path, Model *model,
                      bool& is_cancel,
                      double linear_defletion = 0.003,
                      double angle_defletion = 0.5,
                      bool isSplitCompound = false,
                      ImportStepProgressFn proFn = nullptr,
                      StepIsUtf8Fn isUtf8Fn = nullptr,
                      long& mesh_face_num = *(new long(-1)));

//BBS: Used to detect what kind of encoded type is used in name field of step
// If is encoded in UTF8, the file don't need to be handled, then return the original path directly.
// If is encoded in GBK, then translate to UTF8 and generate a new temporary step file.
// If is encoded in Other type, we can't handled, then treat as UTF8. In this case, the name is garbage
// characters.
// By preprocessing, at least we can avoid garbage characters if the name field is encoded by GBK.
class StepPreProcessor {
    enum class EncodedType : unsigned char
    {
        UTF8,
        GBK,
        OTHER
    };

public:
    bool preprocess(const char* path, std::string &output_path);
    static bool isUtf8File(const char* path);
    static bool isUtf8(const std::string str);
private:
    static bool isGBK(const std::string str);
    static int preNum(const unsigned char byte);
    //BBS: default is UTF8 for most step file.
    EncodedType m_encode_type = EncodedType::UTF8;
};

class StepProgressIncdicator : public Message_ProgressIndicator
{
public:
    StepProgressIncdicator(std::atomic<bool>& stop_flag) : should_stop(stop_flag){}

    Standard_Boolean UserBreak() override { return should_stop.load(); }

    void Show(const Message_ProgressScope&, const Standard_Boolean) override {
        std::cout << "Progress: " << GetPosition() << "%" << std::endl;
    }
private:
    std::atomic<bool>& should_stop;
};

class Step
{
public:
    enum class Step_Status {
        LOAD_SUCCESS,
        LOAD_ERROR,
        CANCEL,
        MESH_SUCCESS,
        MESH_ERROR
    };
    Step(fs::path path, ImportStepProgressFn stepFn = nullptr, StepIsUtf8Fn isUtf8Fn = nullptr);
    Step(std::string path, ImportStepProgressFn stepFn = nullptr, StepIsUtf8Fn isUtf8Fn = nullptr);
    ~Step();
    Step_Status load();
    /* 只走 XCAF 的形狀樹做計數，不做任何幾何運算、不網格化，
       所以可以放在 load() 與 mesh() 之間那個空檔呼叫（Model.cpp 的 step_mesh_fn 就在那裡）。 */
    StepBRepCensus inspect_brep() const;
    unsigned int get_triangle_num(double linear_defletion, double angle_defletion);
    unsigned int get_triangle_num_tbb(double linear_defletion, double angle_defletion);
    void clean_mesh_data();
    Step_Status mesh(Model* model,
                     bool& is_cancel,
                     bool isSplitCompound,
                     double linear_defletion = 0.003,
                     double angle_defletion = 0.5);

    std::atomic<bool> m_stop_mesh;
    void update_process(int load_stage, int current, int total, bool& cancel);
private:
    std::string m_path;
    ImportStepProgressFn m_stepFn;
    StepIsUtf8Fn m_utf8Fn;
    Handle(XCAFApp_Application) m_app = XCAFApp_Application::GetApplication();
    Handle(TDocStd_Document) m_doc;
    Handle(XCAFDoc_ShapeTool) m_shape_tool;
    std::vector<NamedSolid> m_name_solids;
};

}; // namespace Slic3r

#endif /* slic3r_Format_STEP_hpp_ */

# app.py —— 固定四维度：Grammar / Vocabulary / Organization / Reasoning
from flask import Flask, request, render_template_string, abort, jsonify, session, url_for
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
import json
import re

app = Flask(__name__)
app.secret_key = "change-this-secret-in-prod"  # 生产请替换随机字符串

# ====== 配置区 ======
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # ≤ 10MB
SAVE_ROOT = Path(r"./uploads")
SAVE_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTS = {".pdf", ".docx", ".txt"}     # 稿件类型
ALLOWED_FEEDBACK_EXTS = {".txt"}             # 仅接收 evaluate 输出的 .txt（内部是 JSON）

# { upload_id: { "filename": str, "saved_path": str, "feedback_count": int, "latest_rows": list|None } }
STORE = {}

# =================== HTML 模板 ===================
PAGE = """
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <title>上传并开始反馈</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root { --bg:#fff; --muted:#667085; --border:#e5e7eb; --brand:#2f6feb; }
      * { box-sizing: border-box; }
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#fff;}
      /* 两列：左内容 1.2fr，右边板 0.8fr；底部表格横跨两列 */
      .container{max-width:1200px;margin:0 auto;padding:24px;display:grid;grid-template-columns:1.2fr 0.8fr;gap:24px;}
      .card{border:1px solid var(--border); border-radius:14px; background: #fff;}
      .inner{padding:20px;}
      h1{font-size:22px;margin:0 0 12px;}
      h2{font-size:18px;margin:0 0 8px;}
      label{display:block;margin:10px 0 6px;font-weight:600;}
      input[type="file"]{width:100%;padding:10px;border:1px dashed #c7c7c7;border-radius:10px;}
      button{margin-top:14px;padding:10px 16px;border:none;border-radius:10px;background:var(--brand);color:#fff;font-weight:600;cursor:pointer;}
      button:hover{filter:brightness(0.95);}
      .muted{color:var(--muted);font-size:13px;}
      .result{margin-top:16px;padding:12px;background:#f6f8fa;border:1px solid var(--border);border-radius:10px;}
      code{background:#f3f4f6;padding:2px 6px;border-radius:6px;}
      .kv{display:grid;grid-template-columns:120px 1fr;gap:6px 12px;font-size:14px;}
      .pill{display:inline-block;padding:2px 10px;border:1px solid var(--border);border-radius:999px;background:#fff;font-size:12px;}
      .side h2{font-size:18px;margin:0 0 8px;}
      .divider{height:1px;background:var(--border);margin:12px 0;}
      .row{display:flex;gap:8px;flex-wrap:wrap}
      .btn-secondary{background:#0ea5e9;}
      .btn-ghost{background:#fff;color:#0f172a;border:1px solid var(--border);}
      table{width:100%;border-collapse:collapse;margin-top:12px;}
      th, td{border:1px solid var(--border); padding:8px; vertical-align:top; text-align:left; font-size:14px;}
      th{background:#f9fafb;}
      .small{font-size:12px;color:#475569;}
      /* 让表格卡片横跨两列，占满右下区域 */
      .wide{grid-column:1 / -1;}
      @media (max-width: 900px){ .container{grid-template-columns:1fr;} .wide{grid-column:auto;} }
    </style>
  </head>
  <body>
    <div class="container">
      <!-- 左侧：上传 / 当前稿件操作 -->
      <div class="card">
        <div class="inner">
          <h1>上传并开始反馈</h1>
          <form action="{{ url_for('upload') }}" method="post" enctype="multipart/form-data">
            <label for="paper">选择文件（pdf / docx / txt，≤10MB）</label>
            <input id="paper" name="paper" type="file" required />
            <button type="submit">上传</button>
            <div class="muted" style="margin-top:8px;">
              提交后系统将对稿件进行解析与结构化反馈（展示用文案）。<br>
              实际后端此脚本仅做“保存文件到本地”，解析由你的另一个脚本完成。
            </div>
          </form>

          {% if upload_id %}
            <div class="result">
              <div class="kv">
                <div>上传 ID</div><div><code>{{ upload_id }}</code></div>
                <div>文件名</div><div>{{ filename }}</div>
                <div>保存路径</div><div><code>{{ saved_path }}</code></div>
              </div>
              <div class="divider"></div>
              <div class="row">
                <form action="{{ url_for('feedback_next', upload_id=upload_id) }}" method="post">
                  <button class="btn-secondary" type="submit">获取下一轮反馈（+1）</button>
                </form>
                <a class="btn-ghost" href="{{ url_for('api_feedback_status', upload_id=upload_id) }}" target="_blank" style="text-decoration:none;padding:10px 16px;border-radius:10px;">查看JSON状态</a>
              </div>

              <!-- 反馈上传区（.txt） -->
              <div class="divider"></div>
              <h2>上传本轮反馈结果（.txt，evaluate.py 输出）</h2>
              <form action="{{ url_for('upload_feedback_txt', upload_id=upload_id) }}" method="post" enctype="multipart/form-data">
                <label for="fb">选择反馈文件（*.txt，内容为 JSON）</label>
                <input id="fb" name="feedback_txt" type="file" accept=".txt" required />
                <button type="submit">上传并展示</button>
                <div class="small" style="margin-top:6px;">
                  提示：请上传 evaluate.py 生成的 <code>*_feedback.txt</code>（内部为 JSON）。
                </div>
              </form>
            </div>
          {% endif %}
        </div>
      </div>

      <!-- 右侧：次数面板（固定在右上角） -->
      <div class="card side">
        <div class="inner">
          <h2>次数面板</h2>
          <div>本会话上传次数： <span class="pill">{{ session_upload_count }}</span></div>
          {% if upload_id %}
            <div style="margin-top:6px;">该稿件已获取反馈次数： <span class="pill">{{ feedback_count }}</span></div>
          {% else %}
            <div class="muted" style="margin-top:6px;">上传后将显示该稿件的反馈次数。</div>
          {% endif %}
          <div class="divider"></div>
          <div class="muted">
            说明：本页面仅保存文件并展示“第 N 轮反馈”的进度；解析与模型调用请在你自己的“解析脚本”中完成。
          </div>
        </div>
      </div>

      <!-- 底部宽表格：横跨两列，填满右侧下方空白 -->
      {% if upload_id %}
      <div class="card wide">
        <div class="inner">
          {% if latest_rows %}
            <h2>反馈表格（第 {{ feedback_count }} 轮 / 最新）</h2>
            <div class="small">维度：语法 Grammar、词汇 Vocabulary、组织 Organization、推理 Reasoning</div>
            <table>
              <thead>
                <tr>
                  <th style="width:160px;">维度</th>
                  <th>Summary</th>
                  <th>Issues</th>
                  <th>Revision Tips</th>
                </tr>
              </thead>
              <tbody>
                {% for row in latest_rows %}
                  <tr>
                    <td>{{ row["label_cn"] }}<br><span class="small">{{ row["label_en"] }}</span></td>
                    <td>{{ row["summary"] }}</td>
                    <td>
                      {% if row["issues"] %}
                        <ul style="margin:0 0 0 16px;">
                          {% for it in row["issues"] %}
                            <li>{{ it }}</li>
                          {% endfor %}
                        </ul>
                      {% endif %}
                    </td>
                    <td>
                      {% if row["tips"] %}
                        <ul style="margin:0 0 0 16px;">
                          {% for it in row["tips"] %}
                            <li>{{ it }}</li>
                          {% endfor %}
                        </ul>
                      {% endif %}
                    </td>
                  </tr>
                {% endfor %}
              </tbody>
            </table>
          {% else %}
            <div class="muted">尚未上传任何反馈结果。请先在上方“上传本轮反馈结果”。</div>
          {% endif %}
        </div>
      </div>
      {% endif %}
    </div>
  </body>
</html>
"""

# =================== 工具函数 ===================
def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTS

def allowed_feedback_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_FEEDBACK_EXTS

def parse_feedback_text_to_json(text: str):
    """尽量把文本解析成 JSON；若纯 JSON 失败，退回提取第一个 {...}。"""
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None

def json_to_rows_fixed(data: dict):
    """
    把 evaluate 的 JSON 转为固定四维：Grammar / Vocabulary / Organization / Reasoning。
    若只给了 Coherence，则自动映射为 Reasoning。
    """
    fb = data.get("feedback", {}) or {}
    # 统一到 Reasoning
    if "Reasoning" not in fb and "Coherence" in fb:
        fb["Reasoning"] = fb.get("Coherence") or {}

    def sec(name_en, name_cn):
        sec_obj = fb.get(name_en, {}) or {}
        return {
            "label_en": name_en,
            "label_cn": name_cn,
            "summary": (sec_obj.get("summary") or "").strip(),
            "issues": sec_obj.get("issues") or [],
            "tips": sec_obj.get("revision_tips") or [],
        }

    rows = [
        sec("Grammar", "语法"),
        sec("Vocabulary", "词汇"),
        sec("Organization", "组织"),
        sec("Reasoning", "推理"),
    ]
    return rows

# =================== 路由 ===================
@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        PAGE,
        upload_id=None,
        filename=None,
        saved_path=None,
        feedback_count=0,
        session_upload_count=session.get("upload_count", 0),
        latest_rows=None
    )

@app.route("/upload", methods=["POST"])
def upload():
    if "paper" not in request.files:
        abort(400, "未发现文件字段 'paper'")
    f = request.files["paper"]
    if not f or f.filename == "":
        abort(400, "未选择文件")
    if not allowed_file(f.filename):
        abort(400, f"不支持的文件类型：{Path(f.filename).suffix}. 允许：{', '.join(sorted(ALLOWED_EXTS))}")

    filename = secure_filename(f.filename)
    upload_id = str(uuid.uuid4())
    doc_dir = SAVE_ROOT / upload_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    final_path = doc_dir / filename
    f.save(str(final_path))

    session["upload_count"] = session.get("upload_count", 0) + 1
    STORE[upload_id] = {
        "filename": filename,
        "saved_path": str(final_path.resolve()),
        "feedback_count": 0,
        "latest_rows": None,
    }

    return render_template_string(
        PAGE,
        upload_id=upload_id,
        filename=filename,
        saved_path=str(final_path.resolve()),
        feedback_count=STORE[upload_id]["feedback_count"],
        session_upload_count=session["upload_count"],
        latest_rows=None
    )

@app.route("/feedback/<upload_id>/next", methods=["POST"])
def feedback_next(upload_id):
    item = STORE.get(upload_id)
    if not item:
        abort(404, "upload_id 不存在或已清理")
    item["feedback_count"] += 1

    return render_template_string(
        PAGE,
        upload_id=upload_id,
        filename=item["filename"],
        saved_path=item["saved_path"],
        feedback_count=item["feedback_count"],
        session_upload_count=session.get("upload_count", 0),
        latest_rows=item.get("latest_rows")
    )

@app.route("/feedback/<upload_id>/upload_txt", methods=["POST"])
def upload_feedback_txt(upload_id):
    """上传 .txt 反馈文件（evaluate 输出），解析并在下方表格展示（固定四维：Reasoning）"""
    item = STORE.get(upload_id)
    if not item:
        abort(404, "upload_id 不存在或已清理")

    if "feedback_txt" not in request.files:
        abort(400, "未发现文件字段 'feedback_txt'")
    f = request.files["feedback_txt"]
    if not f or f.filename == "":
        abort(400, "未选择反馈文件")
    if not allowed_feedback_file(f.filename):
        abort(400, f"反馈文件类型不支持：{Path(f.filename).suffix}（仅支持 .txt）")

    raw = f.read().decode("utf-8", errors="ignore")
    data = parse_feedback_text_to_json(raw)
    if data is None:
        abort(400, "未能从该 .txt 中解析出合法的 JSON。请上传 evaluate.py 生成的 *_feedback.txt")

    rows = json_to_rows_fixed(data)

    # 更新内存：最新表格 + 轮次数（视为一轮）
    item["latest_rows"] = rows
    item["feedback_count"] = max(item.get("feedback_count", 0), 1)

    return render_template_string(
        PAGE,
        upload_id=upload_id,
        filename=item["filename"],
        saved_path=item["saved_path"],
        feedback_count=item["feedback_count"],
        session_upload_count=session.get("upload_count", 0),
        latest_rows=item["latest_rows"]
    )

@app.route("/feedback/<upload_id>/status", methods=["GET"])
def api_feedback_status(upload_id):
    item = STORE.get(upload_id)
    if not item:
        abort(404, "upload_id 不存在或已清理")
    return jsonify({
        "upload_id": upload_id,
        "filename": item["filename"],
        "saved_path": item["saved_path"],
        "feedback_count": item["feedback_count"],
        "has_latest_feedback": bool(item.get("latest_rows")),
        "dimensions": ["Grammar", "Vocabulary", "Organization", "Reasoning"],
        "hint": "用 /feedback/<upload_id>/upload_txt 上传 *_feedback.txt 后，页面下方会显示表格。"
    })

if __name__ == "__main__":
    app.run(debug=True)

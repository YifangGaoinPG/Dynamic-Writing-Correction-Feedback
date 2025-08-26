# evaluate.py —— 固定四维(Grammar/Vocabulary/Organization/Reasoning) & 保存为本地 .txt
import json, re, unicodedata
from io import BytesIO
from pathlib import Path

from openai import OpenAI, AuthenticationError, RateLimitError, APIError
from docx import Document
from PyPDF2 import PdfReader

# =============== 配置区（这里改） ===============
API_KEY      = "sk-REPLACE_WITH_YOUR_PROJECT_KEY"  # 本地测试可直写；生产建议用环境变量
FILE_PATH    = r"REPLACE_WITH_YOUR_FILE_PATH"
MODEL        = "gpt-5"        # 或 "gpt-5-mini"
MAX_CHARS    = 180_000
MAX_OUTPUT   = 2048           # 返回的最大 tokens（根据需要调整）
# ==============================================

def read_file_text(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    elif suf == ".docx":
        with path.open("rb") as f:
            bio = BytesIO(f.read())
        doc = Document(bio)
        return "\n".join(p.text for p in doc.paragraphs)
    elif suf == ".pdf":
        with path.open("rb") as f:
            bio = BytesIO(f.read())
        reader = PdfReader(bio)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        raise ValueError(f"Unsupported file type: {suf}. Use .txt/.docx/.pdf")

def clean_text_keep_letters_numbers_punct_whitespace(text: str) -> str:
    """仅保留字母/数字/标点/空白并规范段内空白；保留段落。"""
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    kept = []
    for ch in text:
        if ch in (" ", "\n", "\t"):
            kept.append(ch); continue
        cat = unicodedata.category(ch)  # L/N/P
        if cat.startswith(("L", "N", "P")):
            kept.append(ch)
    filtered = "".join(kept)
    paras = filtered.split("\n\n")
    norm = []
    for para in paras:
        joined = " ".join(para.split("\n"))
        joined = re.sub(r"[ \t]{2,}", " ", joined).strip()
        if joined:
            norm.append(joined)
    return "\n\n".join(norm)

def build_prompt(clean_text: str) -> str:
    # 固定四维并强制 Reasoning；不允许输出 JSON 之外的任何文本
    schema_hint = (
        "Return ONLY a valid JSON object with this exact shape:\n"
        "{\n"
        '  "summary": string,\n'
        '  "feedback": {\n'
        '    "Grammar": {"summary": string, "issues": [string], "revision_tips": [string]},\n'
        '    "Vocabulary": {"summary": string, "issues": [string], "revision_tips": [string]},\n'
        '    "Organization": {"summary": string, "issues": [string], "revision_tips": [string]},\n'
        '    "Reasoning": {"summary": string, "issues": [string], "revision_tips": [string]}\n'
        "  }\n"
        "}\n"
        "No prose or explanation outside JSON."
    )
    return (
        "You are a senior professor of English composition.\n"
        "Provide constructive, actionable feedback in English for the student's IELTS-style essay across exactly four aspects:\n"
        "1) Grammar, 2) Vocabulary, 3) Organization, 4) Reasoning.\n"
        "- For each aspect, write:\n"
        "  • Summary (2–4 sentences)\n"
        "  • 3–6 Specific issues (quote short snippets if helpful)\n"
        "  • Revision tips (bullet list, concrete)\n"
        "- Be precise, avoid generic advice. Focus on patterns, not isolated typos.\n"
        "- Keep a professional, encouraging tone. Do NOT rewrite the whole essay.\n\n"
        f"{schema_hint}\n\n"
        "Student essay (cleaned text follows between <essay> tags):\n"
        "<essay>\n"
        f"{clean_text}\n"
        "</essay>"
    )

def ensure_json(text: str):
    """尽量从模型输出中提取 JSON（防止偶尔有前后缀）。"""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"raw": text}

def normalize_reasoning(obj: dict) -> dict:
    """
    输出端统一为 Reasoning：
    - 若 feedback.Coherence 存在且 Reasoning 缺失，则映射过去；
    - 保证四个键都至少存在（空结构），便于前端稳定渲染。
    """
    if not isinstance(obj, dict):
        return {"summary": "", "feedback": {}}
    fb = obj.setdefault("feedback", {})
    if "Reasoning" not in fb and "Coherence" in fb:
        fb["Reasoning"] = fb.get("Coherence") or {}

    def ensure_section(name):
        sec = fb.get(name) or {}
        fb[name] = {
            "summary": (sec.get("summary") or "").strip(),
            "issues": list(sec.get("issues") or []),
            "revision_tips": list(sec.get("revision_tips") or []),
        }

    for k in ("Grammar", "Vocabulary", "Organization", "Reasoning"):
        ensure_section(k)
    obj["feedback"] = fb
    obj["summary"] = (obj.get("summary") or "").strip()
    return obj

def main():
    if not API_KEY or API_KEY.startswith(("sk-REPLACE","sk-proj-REPLACE")):
        print("ERROR: 请先在脚本顶部配置真实 API_KEY。"); return
    file_path = Path(FILE_PATH).expanduser().resolve()
    if not file_path.exists():
        print(f"ERROR: 文件不存在：{file_path}"); return

    # 读取 & 清洗
    clean_text = clean_text_keep_letters_numbers_punct_whitespace(read_file_text(file_path))
    if len(clean_text) > MAX_CHARS:
        clean_text = clean_text[:MAX_CHARS] + "\n\n[Truncated for length]"

    system_msg = (
        "You are a meticulous, fair English composition professor. "
        "Respond in English using only JSON according to the user's instructions."
    )
    user_msg = build_prompt(clean_text)

    client = OpenAI(api_key=API_KEY)

    try:
        resp = client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_output_tokens=MAX_OUTPUT,
        )
        raw = resp.output_text
        data = ensure_json(raw)
        data = normalize_reasoning(data)  # 统一到 Reasoning，再做最小填充

        # 输出 & 保存
        json_text = json.dumps(data, ensure_ascii=False, indent=2)
        print(json_text)
        out_path = Path.cwd() / f"{file_path.stem}_feedback.txt"
        out_path.write_text(json_text + "\n", encoding="utf-8")
        print(f"\nSaved to: {out_path}")

    except AuthenticationError as e:
        print("❌ AuthenticationError（密钥无效/权限问题）：", e)
    except RateLimitError as e:
        code = None
        try:
            code = (getattr(e, "body", {}) or {}).get("error", {}).get("code")
        except Exception:
            pass
        if code == "insufficient_quota":
            print("❌ 429 insufficient_quota：该项目/账号配额为 0（预算打满、未付费或 credits 用尽）。")
        else:
            print("⏳ 429 限流：", e)
    except APIError as e:
        print("❌ APIError：", e)
    except Exception as e:
        print("❌ 未知异常：", e)

if __name__ == "__main__":
    main()


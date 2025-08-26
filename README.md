# IELTS Essay Feedback System

A minimal **Flask app** to upload essays and display structured feedback produced by `evaluate.py`.

Fixed dimensions: **Grammar / Vocabulary / Organization / Reasoning**

---

## **Requirements**
- **Python 3.10+**
- Install dependencies:
```bash
pip install -U flask openai python-docx PyPDF2

## Run the web app

```bash
python app.py
# open http://127.0.0.1:5000
```

- Upload an essay (`.pdf/.docx/.txt`, ≤10MB) → saved to `uploads/<upload_id>/<filename>`.
- Then upload a feedback **.txt** (JSON from `evaluate.py`) → rendered as a table.
- Right panel shows feedback **round count**.

## Generate feedback (local, via OpenAI)

Edit the top of `evaluate.py`:

```python
API_KEY = "sk-..."            # prefer environment variable in production
FILE_PATH = r".../data/sample_essay.docx"
MODEL = "gpt-5"               # or "gpt-5-mini"
```

Run:

```bash
python evaluate.py
# outputs: <essay_stem>_feedback.txt (UTF-8 JSON)
```

`evaluate.py` normalizes any *Coherence* to *Reasoning*, ensuring the 4 fixed sections.

## Feedback JSON format (inside the .txt)

```json
{
  "summary": "string",
  "feedback": {
    "Grammar":      { "summary": "string", "issues": ["string"], "revision_tips": ["string"] },
    "Vocabulary":   { "summary": "string", "issues": ["string"], "revision_tips": ["string"] },
    "Organization": { "summary": "string", "issues": ["string"], "revision_tips": ["string"] },
    "Reasoning":    { "summary": "string", "issues": ["string"], "revision_tips": ["string"] }
  }
}
```

## Routes

| Method | Path                               | Purpose                               | Form field     |
|:------:|------------------------------------|---------------------------------------|----------------|
| GET    | `/`                                | Main page                             | —              |
| POST   | `/upload`                          | Upload essay (saved to disk)          | `paper`        |
| POST   | `/feedback/<upload_id>/upload_txt` | Upload feedback JSON (.txt)           | `feedback_txt` |
| POST   | `/feedback/<upload_id>/next`       | Increment feedback round (UI counter) | —              |
| GET    | `/feedback/<upload_id>/status`     | Current item status (JSON)            | —              |

## Notes

- Files persist on disk under `./uploads`; the in-memory counter resets on app restart.
- Do **not** hardcode secrets in production; use env vars (e.g., `OPENAI_API_KEY`).
- If a feedback file only has `Coherence`, it will display under **Reasoning**.

## License

MIT (or your choice).


"""
PDF / Image → JSON Extractor  (two-phase OCR + LLM, Mistral)
============================================================
Adapted from the standalone extractor for use inside the billing backend.

Pipeline for PDFs:
  Phase 1 – OCR        : All pages OCR-ed in parallel (Mistral OCR)
  Phase 2 – Schema     : ONE LLM call on page 1 → master column list + header
  Phase 3 – Row extract: Per-page LLM calls told the EXACT columns to use
  Phase 4 – Merge      : Simple concatenation (no key normalisation needed)

The bytes-based entry points (`extract_from_pdf_bytes`, `extract_from_image_bytes`,
`extract_from_images_bytes`) are what the upload-bill endpoint calls — uploaded
files never touch disk.

Requires: httpx, PyPDF2, pdfplumber.
"""

import asyncio
import base64
import io
import json
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pdfplumber
from PyPDF2 import PdfReader, PdfWriter

from app.config import settings

# Mistral key: managed via Settings (env var MISTRAL_API_KEY → .env → dev default).
MISTRAL_API_KEY: str = settings.mistral_api_key

IMAGE_MIME_TYPES: Dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".svg":  "image/svg+xml",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".bmp":  "image/bmp",
    ".tiff": "image/tiff",
    ".tif":  "image/tiff",
}


class PdfExtractor:
    """
    Converts PDFs and images to structured JSON.

    Output schema:
    {
        "header":        { ... },  # company, invoice no, date, etc.
        "table_columns": [ ... ],  # exact column names (master schema)
        "items":         [ ... ],  # one dict per row, keys = table_columns
        "summary":       { ... },  # totals, taxes, bank details, terms
        "metadata":      { ... }   # pages, tokens, extraction mode
    }
    """

    OCR_URL   = "https://api.mistral.ai/v1/ocr"
    CHAT_URL  = "https://api.mistral.ai/v1/chat/completions"
    OCR_MODEL = "mistral-ocr-latest"
    LLM_MODEL = "mistral-large-latest"
    TIMEOUT   = 300.0

    def __init__(self, api_key: str = MISTRAL_API_KEY, max_concurrent_ocr: int = 3, max_concurrent_llm: int = 2) -> None:
        self.api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self._max_concurrent_ocr = max_concurrent_ocr
        self._max_concurrent_llm = max_concurrent_llm
        self._ocr_semaphore: Optional[asyncio.Semaphore] = None
        self._llm_semaphore: Optional[asyncio.Semaphore] = None

    # ── Rate-limit helpers ────────────────────────────────────────────────────

    def _get_ocr_semaphore(self) -> asyncio.Semaphore:
        if self._ocr_semaphore is None:
            self._ocr_semaphore = asyncio.Semaphore(self._max_concurrent_ocr)
        return self._ocr_semaphore

    def _get_llm_semaphore(self) -> asyncio.Semaphore:
        if self._llm_semaphore is None:
            self._llm_semaphore = asyncio.Semaphore(self._max_concurrent_llm)
        return self._llm_semaphore

    async def _call_mistral_with_retry(
        self,
        url: str,
        payload: dict,
        headers: dict,
        label: str = "Mistral API",
        sem: Optional[asyncio.Semaphore] = None,
        max_retries: int = 5,
        base_delay: float = 2.0,
    ):
        """POST to a Mistral endpoint, semaphore-limited, retrying on HTTP 429."""
        semaphore = sem if sem is not None else self._get_llm_semaphore()
        async with semaphore:
            for attempt in range(max_retries + 1):
                async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                    response = await client.post(url, json=payload, headers=headers)

                if response.status_code != 429:
                    return response

                if attempt == max_retries:
                    return response  # exhausted — let caller raise

                retry_after = float(
                    response.headers.get("retry-after", base_delay * (2 ** attempt))
                )
                print(
                    f"[WARNING] {label}: Rate limit (429). "
                    f"Retrying in {retry_after:.1f}s… (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(retry_after)

        return response  # type: ignore[return-value]

    # ── Public entry points (bytes-based — no disk I/O) ─────────────────────────

    async def extract_from_pdf_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract structured JSON from raw PDF bytes."""
        result, tokens = await self._process_pdf_bytes(pdf_bytes)
        print(f"[DONE] PDF done — {len(result['items'])} items, {tokens} total tokens")
        return result

    async def extract_from_image_bytes(self, image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """Extract structured JSON from a single image (raw bytes + mime type)."""
        result, tokens = await self._process_single_image(image_bytes, mime_type)
        print(f"[DONE] Image done — {len(result['items'])} items, {tokens} total tokens")
        return result

    async def extract_from_images_bytes(self, image_data: List[Tuple[bytes, str]], filenames: List[str]) -> Dict[str, Any]:
        """Extract structured JSON from multiple images (list of (bytes, mime))."""
        if not image_data:
            raise ValueError("image_data must not be empty.")
        if len(image_data) > 10:
            raise ValueError("Maximum 10 images per call.")
        result, tokens = await self._process_multi_image(image_data, filenames)
        print(f"[DONE] Multi-image done — {len(result['items'])} items, {tokens} total tokens")
        return result

    # ── PDF two-phase pipeline ────────────────────────────────────────────────

    async def _process_pdf_bytes(self, pdf_bytes: bytes) -> Tuple[Dict[str, Any], int]:
        total_pages = self._get_pdf_page_count(pdf_bytes)
        total_tokens = 0

        # Phase 1: OCR all pages in parallel
        ocr_tasks = [self._ocr_one_page(pdf_bytes, i) for i in range(total_pages)]
        ocr_results: List[Tuple[str, List[Dict], int]] = list(await asyncio.gather(*ocr_tasks))
        total_tokens += sum(r[2] for r in ocr_results)

        # Phase 2: Schema discovery (page 1 only)
        master_columns, header, schema_tokens = await self._discover_schema(
            page_markdown=ocr_results[0][0],
            page_table_data=ocr_results[0][1],
            total_pages=total_pages,
        )
        total_tokens += schema_tokens

        # Phase 3: Row extraction with fixed schema (parallel)
        row_tasks = [
            self._extract_rows_from_page(
                markdown=ocr_results[i][0],
                table_data=ocr_results[i][1],
                page_number=i + 1,
                total_pages=total_pages,
                master_columns=master_columns,
                extract_summary=(i == total_pages - 1),
            )
            for i in range(total_pages)
        ]
        row_results: List[Tuple[List[Dict], Dict, int]] = list(await asyncio.gather(*row_tasks))
        total_tokens += sum(r[2] for r in row_results)

        # Phase 4: Merge
        all_items: List[Dict] = []
        for items, _, _ in row_results:
            all_items.extend(items)

        summary: Dict[str, Any] = {}
        for items, page_summary, _ in reversed(row_results):
            for k, v in page_summary.items():
                if k not in summary and v is not None:
                    summary[k] = v

        return {
            "header":        header,
            "table_columns": master_columns,
            "items":         all_items,
            "summary":       summary,
            "metadata": {
                "total_pages":       total_pages,
                "total_tokens_used": total_tokens,
                "extraction_method": "two-phase-ocr-schema-rows",
                "processing_mode":   "parallel",
            },
        }, total_tokens

    async def _ocr_one_page(self, pdf_bytes: bytes, page_num: int) -> Tuple[str, List[Dict], int]:
        page_pdf   = self._extract_pdf_page(pdf_bytes, page_num)
        table_data = self._extract_tables_pdfplumber(pdf_bytes, page_num)
        markdown, tokens = await self._ocr_pdf_page(page_pdf, page_num)
        return markdown, table_data, tokens

    async def _discover_schema(
        self,
        page_markdown: str,
        page_table_data: List[Dict],
        total_pages: int,
    ) -> Tuple[List[str], Dict[str, Any], int]:
        table_section = self._build_table_section(page_table_data)

        prompt = f"""You are analysing PAGE 1 of a {total_pages}-page document.
Your ONLY job here is to establish the document structure so all pages can be processed consistently.

PAGE 1 CONTENT:
{page_markdown}
{table_section}

TASK A — HEADER:
Extract top-level document fields (company name, invoice/PO number, date, address, GST, etc.)
Only include fields that actually exist. Use null for missing values.

TASK B — TABLE COLUMNS:
Identify all leaf-level column names from the main data table.

CRITICAL RULES FOR MULTI-LEVEL HEADERS:
Many invoices use multi-level (hierarchical) headers, e.g.:
  | CGST        | SGST/UGST   | IGST        |
  | Rate | Amt  | Rate | Amt  | Rate | Amt  |
In this case the pdfplumber data may contain empty strings or repeated names.
You MUST:
  1. Combine parent + child to form unique names: "CGST Rate", "CGST Amt", "SGST Rate", "SGST Amt", "IGST Rate", "IGST Amt"
  2. NEVER include empty strings "" in table_columns
  3. NEVER repeat the same column name — every entry must be unique
  4. Use context from the OCR markdown to understand the header hierarchy

{"If STRUCTURED TABLE DATA is provided above → use it to understand the structure, but apply the rules above to produce clean unique column names." if page_table_data else "Extract column names from the OCR markdown."}

OUTPUT (valid JSON only — no markdown fences):
{{
  "header": {{
    "company_name": null,
    "invoice_no": null,
    "date": null
  }},
  "table_columns": [
    // All leaf-level column names, unique, non-empty
    // Example: ["S.No", "Item Code", "HSN", "Qty", "Unit Price", "Taxable Value", "CGST Rate", "CGST Amt", "SGST Rate", "SGST Amt", "Total"]
  ]
}}

RULES:
- Every string in table_columns must be unique and non-empty
- Return ONLY valid JSON"""

        payload = {
            "model":           self.LLM_MODEL,
            "messages":        [{"role": "user", "content": prompt}],
            "temperature":     0.0,
            "response_format": {"type": "json_object"},
        }

        resp = await self._call_mistral_with_retry(
            self.CHAT_URL, payload, self._headers, label="Schema Discovery"
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Schema discovery failed ({resp.status_code}): {resp.text}")

        data    = resp.json()
        content = data["choices"][0]["message"]["content"]
        tokens  = data.get("usage", {}).get("total_tokens", 0)

        try:
            schema = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Schema discovery returned invalid JSON: {e}\n{content}")

        raw_columns = schema.get("table_columns", [])
        header      = schema.get("header", {})

        # Post-process: remove empty strings, deduplicate
        clean: List[str] = [c for c in raw_columns if c and str(c).strip()]
        seen_cols: Dict[str, int] = {}
        master_columns: List[str] = []
        for col in clean:
            if col not in seen_cols:
                seen_cols[col] = 1
                master_columns.append(col)
            else:
                seen_cols[col] += 1
                master_columns.append(f"{col}_{seen_cols[col]}")

        return master_columns, header, tokens

    async def _extract_rows_from_page(
        self,
        markdown: str,
        table_data: List[Dict],
        page_number: int,
        total_pages: int,
        master_columns: List[str],
        extract_summary: bool = False,
    ) -> Tuple[List[Dict], Dict[str, Any], int]:
        table_section  = self._build_table_section(table_data)
        cols_json      = json.dumps(master_columns, ensure_ascii=False)

        example_row = {col: "..." for col in (master_columns[:4] if master_columns else [])}
        if len(master_columns) > 4:
            example_row["..."] = "..."
        example_str = json.dumps(example_row, ensure_ascii=False)

        summary_block = ""
        if extract_summary:
            summary_block = """
  "summary": {
    // Summary/footer fields from this page: totals, taxes, bank details, terms
    // Only include fields that actually exist on this page
    // e.g. "subtotal": 5000, "cgst": 450, "total_amount": 5900
  },"""

        last_page_note = (
            f"{chr(10)}6. This is the LAST page — also extract any SUMMARY / FOOTER information."
            if extract_summary else ""
        )
        table_hint = (
            "If STRUCTURED TABLE DATA is provided above → use those exact cell values for row data."
            if table_data else ""
        )

        prompt = f"""You are extracting TABLE ROW DATA from page {page_number} of {total_pages}.

The master column schema is FIXED — you MUST use exactly these key names:
COLUMNS: {cols_json}

PAGE {page_number} CONTENT:
{markdown}
{table_section}

INSTRUCTIONS:
1. Extract every complete data row from the table on this page.
2. Represent each row as a JSON object.
   - Keys MUST be EXACTLY the strings in COLUMNS above (copy them character-for-character).
   - Use null for any column that has no value in that row.
3. Skip rows where more than 50% of the columns are empty/null (formatting artifacts).
4. Do NOT include the header row itself as a data item.
5. If this page has NO table rows (e.g. it is a cover page or signature page) → return empty "items": [].{last_page_note}

{table_hint}

OUTPUT (valid JSON only — no markdown fences):
{{
  "items": [
    {example_str}
    // ... one object per data row
  ]{summary_block}
}}

COLUMN REMINDER (copy these exactly as JSON keys):
{cols_json}"""

        payload = {
            "model":           self.LLM_MODEL,
            "messages":        [{"role": "user", "content": prompt}],
            "temperature":     0.0,
            "response_format": {"type": "json_object"},
        }

        resp = await self._call_mistral_with_retry(
            self.CHAT_URL, payload, self._headers, label=f"Row Extract (page {page_number})"
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Row extraction failed page {page_number} ({resp.status_code}): {resp.text}")

        data    = resp.json()
        content = data["choices"][0]["message"]["content"]
        tokens  = data.get("usage", {}).get("total_tokens", 0)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[WARNING] Page {page_number}: invalid JSON from LLM — {e}")
            result = {}

        if isinstance(result, list):
            result = {"items": result, "summary": {}}
        elif not isinstance(result, dict):
            result = {"items": [], "summary": {}}

        items   = result.get("items", [])
        summary = result.get("summary", {})

        items = self._filter_incomplete_items(items)
        if master_columns:
            items = [self._enforce_schema(item, master_columns) for item in items]

        return items, summary, tokens

    # ── Image pipeline ────────────────────────────────────────────────────────

    async def _process_single_image(self, image_bytes: bytes, mime_type: str) -> Tuple[Dict[str, Any], int]:
        markdown, ocr_tokens = await self._ocr_image(image_bytes, mime_type)
        structured, llm_tokens = await self._extract_full_single_page(markdown, table_data=None)
        total = ocr_tokens + llm_tokens

        return {
            "header":        structured.get("header", {}),
            "table_columns": structured.get("table_columns", []),
            "items":         structured.get("items", []),
            "summary":       structured.get("summary", {}),
            "metadata": {
                "total_pages":       1,
                "total_tokens_used": total,
                "extraction_method": "ocr-llm-single",
                "processing_mode":   "image",
            },
        }, total

    async def _process_multi_image(
        self,
        image_data: List[Tuple[bytes, str]],
        filenames: List[str],
    ) -> Tuple[Dict[str, Any], int]:
        total_tokens = 0

        ocr_tasks = [self._ocr_image(img_bytes, mime) for img_bytes, mime in image_data]
        ocr_results = list(await asyncio.gather(*ocr_tasks))
        total_tokens += sum(r[1] for r in ocr_results)

        master_columns, header, schema_tokens = await self._discover_schema(
            page_markdown=ocr_results[0][0],
            page_table_data=[],
            total_pages=len(image_data),
        )
        total_tokens += schema_tokens

        row_tasks = [
            self._extract_rows_from_page(
                markdown=ocr_results[i][0],
                table_data=[],
                page_number=i + 1,
                total_pages=len(image_data),
                master_columns=master_columns,
                extract_summary=(i == len(image_data) - 1),
            )
            for i in range(len(image_data))
        ]
        row_results = list(await asyncio.gather(*row_tasks))
        total_tokens += sum(r[2] for r in row_results)

        all_items: List[Dict] = []
        for items, _, _ in row_results:
            all_items.extend(items)

        summary: Dict[str, Any] = {}
        for _, page_summary, _ in reversed(row_results):
            for k, v in page_summary.items():
                if k not in summary and v is not None:
                    summary[k] = v

        return {
            "header":        header,
            "table_columns": master_columns,
            "items":         all_items,
            "summary":       summary,
            "metadata": {
                "total_images":      len(image_data),
                "total_tokens_used": total_tokens,
                "extraction_method": "two-phase-ocr-schema-rows",
                "processing_mode":   "multi-image",
                "filenames":         filenames,
            },
        }, total_tokens

    async def _extract_full_single_page(
        self, markdown: str, table_data: Optional[List[Dict]]
    ) -> Tuple[Dict[str, Any], int]:
        table_section = self._build_table_section(table_data)
        table_hint = "You have STRUCTURED TABLE DATA (use it for precise cell values)." if table_data else ""

        prompt = f"""You are extracting structured data from a document image.
{table_hint}

DOCUMENT CONTENT:
{markdown}
{table_section}

Extract:
1. HEADER — document-level info (company, number, date, addresses, etc.)
2. TABLE COLUMNS — exact column name strings from the table header
3. ITEMS — one object per data row (keys = table column names)
4. SUMMARY — totals, taxes, bank details, terms (if present)

OUTPUT (valid JSON only):
{{
  "header": {{}},
  "table_columns": [],
  "items": [],
  "summary": {{}}
}}

RULES:
- Item keys MUST come from table_columns
- Skip rows where >50% of fields are empty
- Do NOT hallucinate values — use null if unsure
- Return ONLY valid JSON"""

        payload = {
            "model":           self.LLM_MODEL,
            "messages":        [{"role": "user", "content": prompt}],
            "temperature":     0.0,
            "response_format": {"type": "json_object"},
        }

        resp = await self._call_mistral_with_retry(
            self.CHAT_URL, payload, self._headers, label="Full Extract (single image)"
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Full extraction failed ({resp.status_code}): {resp.text}")

        data    = resp.json()
        content = data["choices"][0]["message"]["content"]
        tokens  = data.get("usage", {}).get("total_tokens", 0)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Full extraction returned invalid JSON: {e}")

        if result.get("items"):
            result["items"] = self._filter_incomplete_items(result["items"])

        return result, tokens

    # ── Mistral OCR calls ─────────────────────────────────────────────────────

    async def _ocr_pdf_page(self, page_pdf_bytes: bytes, page_num: int = 0) -> Tuple[str, int]:
        b64 = base64.b64encode(page_pdf_bytes).decode()
        payload = {
            "model": self.OCR_MODEL,
            "document": {
                "type":         "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            },
            "include_image_base64": False,
        }
        return await self._call_ocr_api(payload, label=f"OCR (page {page_num + 1})")

    async def _ocr_image(self, image_bytes: bytes, mime_type: str) -> Tuple[str, int]:
        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": self.OCR_MODEL,
            "document": {
                "type":      "image_url",
                "image_url": f"data:{mime_type};base64,{b64}",
            },
            "include_image_base64": False,
        }
        return await self._call_ocr_api(payload, label="OCR (image)")

    async def _call_ocr_api(self, payload: dict, label: str = "OCR") -> Tuple[str, int]:
        resp = await self._call_mistral_with_retry(
            self.OCR_URL, payload, self._headers,
            label=label,
            sem=self._get_ocr_semaphore(),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Mistral OCR error {resp.status_code}: {resp.text}")

        data     = resp.json()
        tokens   = data.get("usage", {}).get("total_tokens", 0)
        pages    = data.get("pages", [])
        markdown = pages[0].get("markdown", "") if pages else ""
        return markdown, tokens

    # ── PDF utilities ─────────────────────────────────────────────────────────

    def _get_pdf_page_count(self, pdf_bytes: bytes) -> int:
        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)

    def _extract_pdf_page(self, pdf_bytes: bytes, page_num: int) -> bytes:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        writer.add_page(reader.pages[page_num])
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        return buf.read()

    def _extract_tables_pdfplumber(self, pdf_bytes: bytes, page_num: int) -> List[Dict]:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if page_num >= len(pdf.pages):
                    return []
                tables = pdf.pages[page_num].extract_tables()
                if not tables:
                    return []
                result = []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = [str(c).strip() if c else "" for c in table[0]]
                    rows    = [[str(c).strip() if c else "" for c in row] for row in table[1:]]
                    result.append({"headers": headers, "rows": rows})
                return result
        except Exception as exc:
            print(f"[WARNING] pdfplumber failed for page {page_num + 1}: {exc}")
            return []

    # ── Post-processing helpers ───────────────────────────────────────────────

    def _build_table_section(self, table_data: Optional[List[Dict]]) -> str:
        if not table_data:
            return ""
        section = "\n\n=== STRUCTURED TABLE DATA (use for precise cell values) ===\n"
        for idx, tbl in enumerate(table_data, 1):
            section += f"\nTable {idx}:\n"
            section += f"  Headers : {tbl.get('headers', [])}\n"
            section += f"  Rows ({len(tbl.get('rows', []))} total):\n"
            for row in tbl.get("rows", []):
                section += f"    {row}\n"
        section += "\n=== END STRUCTURED TABLE DATA ===\n"
        return section

    def _filter_incomplete_items(self, items: List[Dict]) -> List[Dict]:
        EMPTY = {None, "", "null", "NULL"}
        result: List[Dict] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            total  = len(item)
            filled = sum(1 for v in item.values() if v not in EMPTY)
            ratio  = filled / total if total else 0

            if ratio >= 0.4:
                result.append(item)
            elif result:
                for k, v in item.items():
                    if v not in EMPTY:
                        if result[-1].get(k) in EMPTY:
                            result[-1][k] = v
                        elif isinstance(result[-1][k], str) and isinstance(v, str):
                            result[-1][k] = f"{result[-1][k]} / {v}"

        return result

    def _enforce_schema(self, item: Dict, master_columns: List[str]) -> Dict:
        enforced = {col: None for col in master_columns}
        for k, v in item.items():
            if k in enforced:
                enforced[k] = v
            else:
                for col in master_columns:
                    if k.lower() == col.lower():
                        enforced[col] = v
                        break
        return enforced

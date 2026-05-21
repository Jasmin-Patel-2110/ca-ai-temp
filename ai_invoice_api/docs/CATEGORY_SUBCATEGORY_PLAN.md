# Category & Subcategory Detection Plan for Invoices

## Current State

- DB has `category` and `subcategory` columns (VARCHAR 255)
- Not used in extraction, INSERT, or API responses
- Can be inferred from: product_name, industry, HSN/SAC code, supplier/buyer

---

## Option A: Prompt-Based (Recommended – No Training)

**Effort:** Low | **Accuracy:** Good | **Cost:** Zero

Add category/subcategory to the extraction prompt with a taxonomy. The vision model infers from invoice content (product, HSN, industry).

### 1. Define taxonomy (example)

| Category | Subcategories |
|----------|---------------|
| Textiles | Fabric, Garments, Yarn, Jobwork |
| Jewellery | Gold, Diamond, Silver, Gems |
| Healthcare | Medicines, Medical Equipment, Hospital Supplies |
| Electronics | Phones, Computers, Appliances, Components |
| Construction | Building Materials, Cement, Steel |
| IT Services | Software, Consulting, Hardware |
| Others | General, Misc |

### 2. Update extraction prompt

Add to JSON template and guide:

```json
"category": null,
"subcategory": null,
```

Prompt text: "Infer category from product_name, HSN/SAC, industry. Pick from: Textiles, Jewellery, Healthcare, Electronics, Construction, IT Services, Others. Subcategory refines it (e.g. Jewellery → Diamond)."

### 3. Code changes

- `extraction_service.py`: Add category/subcategory to prompt + _normalize
- `invoice.py`: Add to _INVOICE_COLS, INSERT, update_invoice
- `schemas`: Add to InvoiceData, InvoiceListItem, UpdateInvoiceRequest

---

## Option B: Rule-Based (HSN/SAC + Keywords)

**Effort:** Medium | **Accuracy:** Good for known HSN | **Cost:** Zero

Map HSN/SAC codes (from additional_detail) and product keywords to category/subcategory.

### HSN mapping (GST India – partial)

| HSN Chapter | Category | Examples |
|-------------|----------|----------|
| 71 | Jewellery | 7113 (articles of gold), 7114 (silver) |
| 61–63 | Textiles | Fabrics, garments |
| 30 | Healthcare | Medicines |
| 84–85 | Electronics | Machinery, electrical |
| 25 | Construction | Cement, lime |

### Implementation

1. Extract `hsn_sac_code` from additional_detail
2. Map first 2–4 digits → category
3. Use product_name keywords as fallback
4. Store in category, subcategory

---

## Option C: Fine-Tuning (Training)

**Effort:** High | **Accuracy:** Best (if enough data) | **Cost:** GPU time, labeling

### Requirements

- 500–2000+ labeled invoices (category, subcategory)
- GPU (24GB+ VRAM: g6.xlarge or similar; 16GB can work with Qwen2-VL-2B)
- LLaMA-Factory for LoRA fine-tuning
- Define category/subcategory taxonomy before labeling

---

### Step 1: Data Collection & Labeling

1. **Export invoices** from DB with doc_id, product_name, industry, additional_detail
2. **Label manually**: For each invoice, assign category + subcategory (e.g. Textiles → Fabric)
3. **Image source**:
   - Images: download from S3 via `documents.s3_key` (linked by `doc_id`)
   - PDFs: render each page with PyMuPDF (one invoice row = one page), save as JPEG
4. **Store labels** in DB: update `category`, `subcategory` columns, or use a separate CSV/JSON for training

**Labeling tools**: Spreadsheet with invoice_id, doc_id, image_url/path, category, subcategory. Or build a simple UI that shows invoice image + dropdowns for category/subcategory.

---

### Step 2: Dataset Format (LLaMA-Factory)

LLaMA-Factory requires **Alpaca** or **ShareGPT** format with an `images` column. Use `<image>` in the text where the image goes; the number of `<image>` tags must match the number of image paths.

**Alpaca format** (for `data/invoice_category_train.json`):

```json
[
  {
    "instruction": "Classify the category and subcategory of this invoice. Return JSON only.",
    "input": "<image>",
    "output": "{\"category\": \"Textiles\", \"subcategory\": \"Fabric\"}",
    "images": ["images/inv_001.jpg"]
  }
]
```

**ShareGPT format** (alternative):

```json
[
  {
    "conversations": [
      {"from": "human", "value": "What is the category and subcategory of this invoice? Return JSON: {\"category\": \"...\", \"subcategory\": \"...\"}<image>"},
      {"from": "gpt", "value": "{\"category\": \"Textiles\", \"subcategory\": \"Fabric\"}"}
    ],
    "images": ["images/inv_001.jpg"]
  }
]
```

**Image rules**:
- Resize to max 1024px (longest side) to reduce memory and speed training
- Store under `data/images/` or a path referenced in the JSON
- Paths in `images` are relative to the project or absolute

---

### Step 3: Export Script (Invoice API → Training Data)

Create `scripts/export_training_data.py`:

1. Query invoices where `category` and `subcategory` are not null
2. Join with documents to get s3_key
3. Download from S3 (or use local files if testing) into `training_data/images/`
4. For PDFs: render pages with PyMuPDF, save each page as `{invoice_id}_page{N}.jpg`
5. Output `training_data/invoice_category_train.json` in Alpaca format

---

### Step 4: dataset_info.json (LLaMA-Factory)

In `LLaMA-Factory/data/dataset_info.json` add:

```json
"invoice_category": {
  "file_name": "invoice_category_train.json",
  "columns": {
    "prompt": "instruction",
    "query": "input",
    "response": "output",
    "images": "images"
  }
}
```

Or for ShareGPT:

```json
"invoice_category": {
  "file_name": "invoice_category_train.json",
  "formatting": "sharegpt",
  "columns": {
    "messages": "conversations",
    "images": "images"
  },
  "tags": {
    "role_tag": "from",
    "content_tag": "value",
    "user_tag": "human",
    "assistant_tag": "gpt"
  }
}
```

---

### Step 5: Training (LLaMA-Factory)

```bash
# Install LLaMA-Factory
git clone https://github.com/hiyouga/LLaMA-Factory
cd LLaMA-Factory
pip install -e .

# Run SFT (example: Qwen2-VL-2B, 24GB GPU)
llamafactory-cli train \
  --stage sft \
  --do_train \
  --model_name_or_path Qwen/Qwen2-VL-2B-Instruct \
  --dataset invoice_category \
  --template qwen2_vl \
  --finetuning_type lora \
  --lora_target all \
  --output_dir ./output/invoice_category_lora \
  --per_device_train_batch_size 2 \
  --gradient_accumulation_steps 4 \
  --learning_rate 5e-5 \
  --num_train_epochs 3 \
  --max_samples 500 \
  --cutoff_len 4096
```

**For qwen2.5vl:7b** (needs ~24GB VRAM, or use 4-bit quantization):
- Use `Qwen/Qwen2.5-VL-7B-Instruct` as base
- Reduce batch size to 1 and increase gradient_accumulation_steps
- Optional: `finetuning_type qlora` for lower memory

---

### Step 6: Merge LoRA & Deploy to Ollama

1. **Merge adapter into base model**:

```bash
llamafactory-cli export \
  --model_name_or_path Qwen/Qwen2-VL-2B-Instruct \
  --adapter_name_or_path ./output/invoice_category_lora \
  --template qwen2_vl \
  --finetuning_type lora \
  --export_dir ./merged_invoice_category
```

2. **Convert to GGUF** (for Ollama): Use `llama.cpp` or `convert_hf_to_gguf.py` if available for Qwen2-VL.

3. **Ollama Modelfile**: Create a Modelfile that uses the merged/GGUF model, then `ollama create invoice-category-model -f Modelfile`.

4. **API integration**: Set `OLLAMA_MODEL=invoice-category-model` (or keep base model and use a two-step flow: base extraction + category model).

---

### Step 7: Integration Options

**A. Single model**: Fine-tune full extraction (incl. category) and replace current `qwen2.5vl:7b` with the fine-tuned model. One API call does everything.

**B. Two-step**: Keep current extraction; add a second Ollama model call for category-only classification. Pass the invoice image (or reuse the same base64 from extraction) to the category model.

---

### Alternative: Lightweight Text Classifier

Train a BERT/RoBERTa classifier on **text only** (product_name + industry + HSN from additional_detail) → category. No images. Cheaper and faster, but misses visual cues. Use when most category signal is in text.

---

## Recommended Path

1. **Phase 1:** Implement Option A (prompt-based) – 1–2 hours
2. **Phase 2:** Add Option B (HSN mapping) as fallback – 2–3 hours
3. **Phase 3 (optional):** If accuracy is insufficient, consider Option C

---

## Implementation Checklist (Option C – Implemented)

- [x] Add category, subcategory to _INVOICE_COLS, create_invoice INSERT
- [x] Add to update_invoice allowed fields
- [x] Add to schemas (InvoiceData, InvoiceListItem, UpdateInvoiceRequest)
- [x] Add GET /invoices/categories endpoint (taxonomy for labeling)
- [x] Create export script: `scripts/export_training_data.py`
- [x] Add OLLAMA_CATEGORY_MODEL integration (calls fine-tuned model when set)
- [ ] Label 500+ invoices (PATCH /invoices/{id} with category, subcategory)
- [ ] Run export script, copy output to LLaMA-Factory data/
- [ ] Fine-tune with LLaMA-Factory
- [ ] Create Ollama model from merged adapter
- [ ] Set OLLAMA_CATEGORY_MODEL=your-model in .env

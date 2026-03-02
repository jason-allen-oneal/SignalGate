# SignalGate - KNN Dataset Contract

This defines the on-disk contract for labeled examples used to train/serve the embedding + KNN tier classifier.

Design goals
- Simple, append-only, diffable
- No raw prompts stored by default
- Deterministic rebuild and rollback

---

## 1) File format
### 1.1 Dataset file
- Format: JSON Lines (jsonl)
- One record per line
- Path: configurable (example: `data/knn_dataset.jsonl`)

### 1.2 Record schema (high level)
Each line is a JSON object with:
- `id` (string) - stable unique id (recommend: sha256 of canonical input representation)
- `label` (string) - `budget` | `balanced` | `premium`
- `embedding` (array[number]) - embedding vector
- `created_at` (string) - ISO-8601 timestamp

Optional:
- `meta` (object) - safe annotations (no secrets)
  - `source` (string) - e.g. "manual", "import", "auto"
  - `notes` (string)
  - `tags` (array[string])

Forbidden by default:
- raw prompt text
- tool schemas
- secrets

---

## 2) Canonical input representation
To generate `id` and embeddings, define a stable representation function:
- Include the last N user messages (N configurable) and exclude assistant responses.
- Include a compact marker for request shape, e.g. `tools_present=true` and `json_required=true`.
- Do not include tool definitions or any secret-bearing content.

This representation must be versioned (so you can rebuild embeddings consistently).

---

## 3) Labeling workflow
Minimum workflow:
1) Collect request ids + hashes from production logs.
2) Sample and label into {budget, balanced, premium}.
3) Embed the canonical representation.
4) Append to `knn_dataset.jsonl`.
5) Rebuild ANN/KNN index.
6) Run offline eval (confusion matrix) before enabling classifier.

Rollback:
- Keep the previous dataset + index version available.
- Revert by switching `knn_index_path` and `knn_dataset_path`.

---

## 4) Versioning
- Dataset version: include in filename or directory (example: `data/datasets/2026-03-01/knn_dataset.jsonl`).
- Index version: tied to dataset version + embedding model.
- Any change to:
  - embedding model
  - canonical representation
  - dataset content
  must bump `_signalgate.router_version` components.

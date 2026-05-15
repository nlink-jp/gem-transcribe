# RFP: gem-transcribe

> Generated: 2026-05-15
> Status: Draft

## 1. Problem Statement

Vertex AI Gemini を活用した「文字起こし基盤」CLI。会議・打合せの記録者、インタビュー / 取材者、字幕・翻訳ワークフロー担当者、ビデオ教材コンテンツの整理者などが、音声ファイルから話者推論つき・構造化・多言語対応のトランスクリプトを得るためのツール。`meeting-note`（議事録構造化ツール）の上流に位置付け、議事録化・要約・アクションアイテム抽出は責務外とする。

主軸は **「文字起こし基盤」** に絞り、UNIX 哲学に沿ってパイプ連携しやすい単機能 CLI として設計する。

## 2. Functional Specification

### Commands / API Surface

```
gem-transcribe <audio-file | gs://bucket/path> [flags]
```

主要フラグ:

| フラグ | 説明 |
|---|---|
| `--lang=en,ja` | 出力言語。複数指定で原文+翻訳を同時出力 |
| `--speaker-hint="山田,佐藤"` | 話者ヒント。プロンプトに渡し、Gemini に名前割当を試みさせる |
| `--format=json\|md\|srt\|vtt\|text` | 出力フォーマット。デフォルト json |
| `--output-dir=<dir>` | 複数フォーマットを一括出力 |
| `--output-file=<path>` | 単一ファイル出力先 |
| `--model=flash\|pro` | 使用モデル。デフォルトは config.toml の値 |
| `--keep-staging` | GCS ステージング上の音声ファイルを削除しない（デバッグ用） |
| `--config=<path>` | config.toml パス上書き |

### Input / Output

**入力:**
- ローカル音声ファイル（mp3, wav, m4a, flac, ogg 等 Gemini がサポートする形式）
  → ツールが自動で `staging_bucket` 配下にアップロード、処理後デフォルトで削除
- `gs://bucket/path/audio.mp3`（事前アップロード済 GCS URI）
  → アップロードスキップ、削除もしない

**出力:**
- デフォルト: stdout に JSON
- `--output-dir` 指定時: `<input-basename>.{json,md,srt,vtt,txt}` を一括生成
- `--output-file` 指定時: 単一ファイルに `--format` で書き出し

**JSON スキーマ（暫定）:**

```json
{
  "metadata": {
    "source": "meeting-2026-05-15.mp3",
    "model": "gemini-2.5-flash",
    "duration_seconds": 1825.4,
    "languages": ["en", "ja"],
    "speaker_hints": ["Yamada", "Sato"]
  },
  "segments": [
    {
      "start": 0.0,
      "end": 4.2,
      "speaker": "Yamada",
      "text": {
        "en": "Let's review the quarterly results.",
        "ja": "四半期業績を見ていきましょう。"
      }
    }
  ]
}
```

### Configuration

`config.toml`（既存 11 ツールの統一パターンに準拠）:

```toml
[vertex_ai]
project_id = "your-gcp-project"
location = "us-central1"
model = "gemini-2.5-flash"

[storage]
staging_bucket = "gs://your-bucket/gem-transcribe/"

[transcribe]
default_languages = ["en"]
keep_staging = false
```

環境変数オーバーライドも nlk-py 規約に従う（`GEM_TRANSCRIBE_*` プレフィックス）。

### External Dependencies

- **Vertex AI Gemini API**（必須）
- **Google Cloud Storage**（必須、ステージング用バケット）
- **Python 3.11+**
- **google-genai SDK**（Vertex AI モード）
- **nlk-py**（guard / jsonfix / backoff / validate）
- **ffmpeg**（Phase 2 のチャンク化機能のみ。Phase 1 では不要）

## 3. Design Decisions

### なぜ Python か

長尺音声の分割処理が将来必要になった場合、Python は `pydub` や `ffmpeg-python`、`pydub.silence` 等で無音検出ベースの賢いチャンク化が容易。Go は ffmpeg シェルアウト + 自前パースが必要で、音声ドメインのエコシステム差が大きい。

加えて、`meeting-note`（Python / Vertex AI）と同じ言語のため、JSON スキーマや共通プロンプトの流用が効く。`nlk-py` 統合パターンも meeting-note / mail-triage / ai-ir2 / gem-rag で実証済み。

### なぜ既存ツールを補完する位置付けか

- **meeting-note**: 議事録構造化・要約は meeting-note に任せ、gem-transcribe → meeting-note とパイプ連携する設計。スキーマ互換は緊密に保証せず、必要なら間に変換ステージを挟む。
- **gem-* ファミリー**: util-series の Gemini 系 CLI 群（gem-search / gem-image / gem-query / gem-rag）と命名・config.toml パターンを揃える。

### スコープ外（明示的に除外）

- リアルタイムストリーミング文字起こし（マイク入力のリアルタイム処理は制御複雑化・スコープ拡大）
- 議事録・要約・アクションアイテム抽出（meeting-note の責務）
- 音声ファイルの事前処理（ノイズ除去・音量調整・フォーマット変換）— 生ファイルを Vertex AI に渡し Gemini の頑健性に委ねる
- WebUI / GUI（CLI 主軸。GUI が必要になったら shell-agent / data-agent パターンで別途設計）

## 4. Development Plan

### Phase 1: Core

- 単一ファイル文字起こし（ローカル/GCS 両対応）
- 話者推論（A/B/C ラベル + ヒント名前割当の両対応、ヒントは optional）
- マルチランゲージ出力（`--lang=en,ja` で原文+翻訳を同時生成）
- JSON 出力 + Plain text 出力
- `config.toml` + ADC 認証
- 自動 GCS アップロード/削除、`--keep-staging` フラグ
- nlk-py/jsonfix による LLM 応答の堅牢パース
- nlk-py/backoff によるレート制限耐性
- 9.5 時間超の音声に対する明示的エラー
- pytest によるテスト（プロンプト構築 / レスポンスパース / GCS アップロード等の単体テスト中心、E2E は実音声で別途）

### Phase 2: Features

- Markdown / SRT / VTT フォーマッタ（JSON からのポストプロセス、`--format` フラグ切替）

### Phase 3: Release

- README.md / README.ja.md 整備
- CHANGELOG.md
- AGENTS.md
- 実音声での E2E テスト（短尺・中尺・多言語ケース）
- v0.1.0 リリース

各 Phase は独立してレビュー可能。Phase 1 が安定した時点で util-series サブモジュールとして取り込む（CONVENTIONS.md `_wip/` ワークフロー）。

## 5. Required API Scopes / Permissions

- **Vertex AI User** (`roles/aiplatform.user`) — Gemini API 呼出し
- **Storage Object Admin** (`roles/storage.objectAdmin`) — ステージングバケット書込/読取/削除
  - 最小権限なら `objectCreator` + `objectViewer` + `objectAdmin`（削除のため）の組合せ
- ユーザー事前準備:
  - GCS バケットを作成（リージョンは Vertex AI と同一推奨）
  - `gcloud auth application-default login` で ADC 設定

## 6. Series Placement

**Series: util-series**

理由:
- パイプ友好なデータ変換 CLI（音声 → 構造化テキスト）
- 既存の Gemini 系兄弟（gem-search / gem-image / gem-query / gem-rag）と完全に揃う
- meeting-note 等の他ツールと組み合わせやすい
- 自分中心の利用で、配布形態は pip / uv tool でよい

`lab-series` は実験段階のためのバケットだが、要件と設計方針が固まっているため最初から util-series 配下で良い。

## 7. External Platform Constraints

### Vertex AI Gemini

- **レート制限**: QPM / TPM 上限あり。バッチ処理時 429 多発の事例（`feedback_gemini_api_rate_limit`）→ nlk-py/backoff で指数バックオフ
- **音声サポート上限**: 〜9.5 時間 / リクエスト。超過時は Phase 1 では明示的エラー、Phase 2 でチャンク化（pydub.silence + ffmpeg）対応を検討
- **Files API 不可**: Vertex AI では `files.upload()` が使えない（`feedback_vertex_files_upload`）→ 必ず `Part.from_uri(gs://...)` 経由
- **Gemini 3 移行**: 2026-10-16 以降 GA 予定。他 13 ツールと一括移行（`project_gemini3_migration` メモリに本ツールを追記）。移行時は thought signature の echo back 対応も必要（`feedback_gemini3_thought_signature`）

### GCS

- ユーザーがバケットを事前作成・IAM 付与する必要。ツール側ではバケット作成しない（README に手順明記）

### ローカル依存

- ffmpeg は Phase 2 チャンク化機能の有効時のみ必要。Phase 1 では不要

### モデル選択

- デフォルト: `gemini-2.5-flash`（コスト重視、話者推論も実用レベル）
- `config.toml` で `gemini-2.5-pro` に切替可能（複雑な話者分離・多言語ケース）

---

## Discussion Log

### 2026-05-15 — 初回 RFP 策定

**ツール名選定:**
- 候補: gem-voice / gem-transcribe / gem-stt / gem-scribe
- → `gem-transcribe`（用途が明確、既存 gem-* ファミリーと整合）

**Problem Statement の絞り込み:**
- 「多目的オールインワン」案も検討したが、スコープ拡散リスクが高いため却下
- → **「文字起こし基盤」に絞る**ことで meeting-note との責務分離を明確化

**話者推論レベル:**
- ラベルのみ / ヒント付き名前推論 / 両方対応
- → **両方対応（ヒント optional）**。プロンプト設計で柔軟に分岐

**入力手段の論点:**
- 当初 inline base64 + 自動 GCS 切替を案として提示
- ユーザー指摘により **GCS バケット経由を基本路線**に修正（base64 inline は長尺で実用性に欠ける）
- ローカルファイルは内部で staging bucket に自動アップロード → 処理後デフォルト削除

**実装言語の検討:**
- Go（gem-* 一族との見栄え統一）vs Python（音声エコシステム優位）
- 長尺音声のチャンク化観点で Python 優位（pydub / pydub.silence）
- meeting-note との JSON スキーマ流用、nlk-py 統合パターン実績
- → **Python を選定**。命名規則の見栄えのために音声ドメインで Go を選ぶのは本末転倒

**スコープ外の確定:**
- リアルタイムストリーミング、議事録/要約/アクションアイテム抽出、音声前処理、WebUI/GUI

**Phase 1 / Phase 2 の切り分け:**
- Phase 1: 単一ファイル文字起こし + 話者推論 + マルチランゲージ + JSON
- Phase 2: Markdown / SRT / VTT フォーマッタ
- 自動チャンク化・バッチ処理・話者プロファイル保存は将来検討

**Series Placement:**
- util-series（パイプ友好、gem-* ファミリーと整合）
- lab-series 経由は不要（要件・設計が固まっているため）

**外部制約の記録:**
- Vertex AI レート制限、GCS 事前準備、9.5 時間上限、ffmpeg ローカル依存（Phase 2）
- Gemini 3 移行は他ツールと一括対応（記録のみ）

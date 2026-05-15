# gem-transcribe

Vertex AI Gemini を活用した音声文字起こし CLI。話者推論、マルチランゲージ出力、構造化 JSON に対応します。

`gem-transcribe` は「文字起こし基盤」に特化した単機能ツールです。議事録の構造化、要約、アクションアイテム抽出は下流の
[meeting-note](https://github.com/nlink-jp/meeting-note) などに任せます。

## 主な機能

- **話者推論** — デフォルトで音声内の自己紹介・呼びかけ・第三者言及から話者の名前を抽出します。名前が特定できない話者は `Speaker A`, `Speaker B`, ... のラベルにフォールバック。`--speaker-hint="山田,佐藤"` を渡すと候補名を限定できます
- **マルチランゲージ出力** — `--lang=en,ja` のように指定すると、原文と翻訳を 1 回の API 呼び出しで同時生成
- **長尺音声対応** — ローカルファイルは GCS ステージングバケットに自動アップロードされ、処理後に削除されます。事前アップロード済みの `gs://` URI もそのまま受け付けます
- **複数の出力フォーマット** — デフォルトは stdout への JSON。`--format text|md|srt|vtt` で他形式に切り替え可能。SRT/VTT を `--output-file=meeting.srt --lang=en,ja` のように多言語指定すると `meeting.en.srt` と `meeting.ja.srt` が自動生成されます。`--output-dir` は `.json` と `.txt` の両方を一括出力

## インストール

```bash
uv tool install git+https://github.com/nlink-jp/gem-transcribe.git
# または、クローンから
uv sync --all-extras
```

Python 3.11+ が必要です。

## セットアップ

1. **GCS バケットの作成**（ステージング用）:

   ```bash
   gsutil mb -l us-central1 gs://your-bucket
   ```

2. **ADC（Application Default Credentials）の設定**:

   ```bash
   gcloud auth application-default login
   ```

3. **設定ファイルの作成** — `~/.config/gem-transcribe/config.toml`
   （テンプレートは `config.example.toml` 参照）:

   ```toml
   [gcp]
   project = "your-gcp-project"
   location = "us-central1"

   [model]
   name = "gemini-2.5-flash"

   [storage]
   staging_bucket = "gs://your-bucket/gem-transcribe/"
   ```

   IAM プリンシパルには `roles/aiplatform.user` と、ステージングバケットへの `roles/storage.objectAdmin` が必要です。

## 使い方

```bash
# JSON を stdout に出力（デフォルト）
gem-transcribe meeting.mp3

# 多言語出力
gem-transcribe interview.m4a --lang=en,ja

# 話者名の割り当て
gem-transcribe meeting.mp3 --speaker-hint="山田,佐藤,田中"

# JSON とプレーンテキストの両方をディレクトリに出力
gem-transcribe meeting.mp3 --output-dir=./transcripts/

# Markdown タイムライン
gem-transcribe meeting.mp3 --format=md --output-file=meeting.md

# SRT 字幕
gem-transcribe meeting.mp3 --format=srt --output-file=meeting.srt

# 多言語 SRT — meeting.en.srt と meeting.ja.srt が生成される
gem-transcribe meeting.mp3 --lang=en,ja --format=srt --output-file=meeting.srt

# WebVTT 字幕（<v Speaker> voice タグ付き）
gem-transcribe meeting.mp3 --format=vtt --output-file=meeting.vtt

# 事前アップロード済みの GCS 音声
gem-transcribe gs://your-bucket/recordings/2026-05-15.mp3
```

## 設定の優先順位

高 → 低:

1. CLI フラグ
2. 環境変数（`GEM_TRANSCRIBE_*`）
3. `.env` ファイル
4. `~/.config/gem-transcribe/config.toml`
5. 組み込みデフォルト値

## ビルドとテスト

```bash
make test     # uv run pytest tests/ -v
make lint     # ruff check + format check
make build    # uv build --out-dir dist/
```

## ドキュメント

- [docs/ja/gem-transcribe-rfp.ja.md](docs/ja/gem-transcribe-rfp.ja.md) — 設計 RFP
- [docs/en/gem-transcribe-rfp.md](docs/en/gem-transcribe-rfp.md) — design RFP

## ライセンス

MIT

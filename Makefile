.DEFAULT_GOAL := help

PYTHON ?= python
PIP ?= $(PYTHON) -m pip
DOUYIN ?= douyin-dl
CONFIG ?= config.yml
HOST ?= 127.0.0.1
PORT ?= 8000

INPUT ?=
OUTPUT ?=
VIDEO ?=
SRT ?=
ASS ?=
OUTPUT_DIR ?= ./subtitle_outputs
TRANSLATOR ?= noop
SOURCE_LANG ?= zh
TARGET_LANG ?= vi
BATCH_SIZE ?= 20
STYLE ?= douyin_vi
MASK_MODE ?= none
MASK_RECT ?=
MASK_JSON ?= mask_rect.json
TIME ?= 00:00:03
FFMPEG ?= ffmpeg
FONTS_DIR ?=
TRANSCRIBE_DIR ?= ./Downloaded
FUNASR_ARGS ?= -d "$(TRANSCRIBE_DIR)" --srt
SENSEVOICE_ARGS ?= -d "$(TRANSCRIBE_DIR)" --srt
WHISPER_ARGS ?= -d "$(TRANSCRIBE_DIR)" --srt

.PHONY: help install-dev install-all test lint lint-new check clean serve \
	subtitle-tests subtitle-lint subtitle-check subtitle-translate subtitle-ass \
	subtitle-pick subtitle-burn subtitle-pipeline \
	install-transcribe-whisper install-transcribe-funasr install-transcribe-sensevoice install-transcribe-opencc install-transcribe-all \
	funasr-transcribe sensevoice-transcribe whisper-transcribe

help:
	@echo "Common targets:"
	@echo "  make install-dev        Install editable dev + server dependencies"
	@echo "  make install-all        Install editable all extras"
	@echo "  make test               Run full pytest suite"
	@echo "  make lint               Run ruff on full repo"
	@echo "  make lint-new           Run ruff on subtitle/API additions"
	@echo "  make check              Run lint-new + full tests"
	@echo "  make serve              Run REST API server"
	@echo ""
	@echo "Transcribe targets:"
	@echo "  make install-transcribe-whisper"
	@echo "  make install-transcribe-funasr"
	@echo "  make install-transcribe-sensevoice"
	@echo "  make install-transcribe-opencc"
	@echo "  make install-transcribe-all"
	@echo "  make funasr-transcribe FUNASR_ARGS='-d ./Downloaded --srt'"
	@echo "  make whisper-transcribe WHISPER_ARGS='-d ./Downloaded --srt'"
	@echo "  make sensevoice-transcribe SENSEVOICE_ARGS='-d ./Downloaded --srt --sense-voice ./model.int8.onnx --tokens ./tokens.txt --silero-vad-model ./silero_vad.onnx'"
	@echo ""
	@echo "Subtitle targets:"
	@echo "  make subtitle-tests"
	@echo "  make subtitle-lint"
	@echo "  make subtitle-check"
	@echo "  make subtitle-translate INPUT=in.srt OUTPUT=out.vi.srt"
	@echo "  make subtitle-ass INPUT=out.vi.srt OUTPUT=out.vi.ass"
	@echo "  make subtitle-pick VIDEO=in.mp4 TIME=00:00:03"
	@echo "  make subtitle-burn VIDEO=in.mp4 ASS=out.vi.ass OUTPUT=out.mp4 MASK_MODE=blur MASK_RECT=0,880,1080,180"
	@echo "  make subtitle-pipeline VIDEO=in.mp4 SRT=in.srt OUTPUT=out.mp4 MASK_MODE=blur MASK_RECT=0,880,1080,180"

install-dev:
	$(PIP) install -e ".[dev,server]"

install-all:
	$(PIP) install -e ".[all]"

install-transcribe-whisper:
	$(PIP) install -e ".[transcribe]"

install-transcribe-funasr:
	$(PIP) install -e ".[transcribe-funasr]"

install-transcribe-sensevoice:
	$(PIP) install -e ".[transcribe-sensevoice]"

install-transcribe-opencc:
	$(PIP) install -e ".[transcribe-opencc]"

install-transcribe-all:
	$(PIP) install -e ".[transcribe,transcribe-funasr,transcribe-sensevoice,transcribe-opencc]"

test:
	$(PYTHON) -m pytest tests

lint:
	$(PYTHON) -m ruff check .

lint-new:
	$(PYTHON) -m ruff check subtitle cli/subtitle_commands.py server/subtitle_api.py server/subtitle_jobs.py tests/test_subtitle_*.py

check: lint-new test

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

serve:
	$(DOUYIN) --serve --serve-host $(HOST) --serve-port $(PORT) --config $(CONFIG)

subtitle-tests:
	$(PYTHON) -m pytest tests/test_subtitle_*.py

subtitle-lint:
	$(PYTHON) -m ruff check subtitle cli/subtitle_commands.py server/subtitle_api.py server/subtitle_jobs.py tests/test_subtitle_*.py

subtitle-check: subtitle-lint subtitle-tests

subtitle-translate:
	$(DOUYIN) translate-srt --input "$(INPUT)" --output "$(OUTPUT)" --source-lang "$(SOURCE_LANG)" --target-lang "$(TARGET_LANG)" --translator "$(TRANSLATOR)" --batch-size "$(BATCH_SIZE)"

subtitle-ass:
	$(DOUYIN) srt-to-ass --input "$(INPUT)" --output "$(OUTPUT)" --style-preset "$(STYLE)"

subtitle-pick:
	$(DOUYIN) pick-mask-rect --video "$(VIDEO)" --timestamp "$(TIME)" --output "$(MASK_JSON)" --ffmpeg-path "$(FFMPEG)"

subtitle-burn:
	$(DOUYIN) burn-sub --video "$(VIDEO)" --ass "$(ASS)" --output "$(OUTPUT)" --ffmpeg-path "$(FFMPEG)" --fonts-dir "$(FONTS_DIR)" --mask-mode "$(MASK_MODE)" --mask-rect "$(MASK_RECT)"

subtitle-pipeline:
	$(DOUYIN) subtitle-pipeline --video "$(VIDEO)" --srt "$(SRT)" --output "$(OUTPUT)" --output-dir "$(OUTPUT_DIR)" --source-lang "$(SOURCE_LANG)" --target-lang "$(TARGET_LANG)" --translator "$(TRANSLATOR)" --batch-size "$(BATCH_SIZE)" --style-preset "$(STYLE)" --mask-mode "$(MASK_MODE)" --mask-rect "$(MASK_RECT)" --ffmpeg-path "$(FFMPEG)" --fonts-dir "$(FONTS_DIR)"

funasr-transcribe:
	$(PYTHON) cli/funasr_transcribe.py $(FUNASR_ARGS)

sensevoice-transcribe:
	$(PYTHON) cli/sensevoice_transcribe.py $(SENSEVOICE_ARGS)

whisper-transcribe:
	$(PYTHON) cli/whisper_transcribe.py $(WHISPER_ARGS)

# Hướng dẫn CLI/Makefile cho AI agent và maintainer

Tài liệu này gom các lệnh thường dùng của repo để AI agent hoặc maintainer có thể setup, test, chạy downloader, API server và subtitle pipeline mà không phải đọc rải rác nhiều file.

## 1. Cài đặt nhanh

```bash
python -m pip install -e ".[dev,server]"
```

Nếu cần browser fallback hoặc lấy cookie bằng Playwright:

```bash
python -m pip install -e ".[browser,dev,server]"
python -m playwright install chromium
```

Nếu cần subtitle local đầy đủ:

```bash
python -m pip install -e ".[dev,server,subtitle,translate-local]"
```

Ý nghĩa extras:

| Extra | Khi dùng | Ghi chú |
| --- | --- | --- |
| `dev` | chạy test/lint | cài `pytest`, `ruff`, `httpx` |
| `server` | chạy REST API | cài `fastapi`, `uvicorn`, `pydantic` |
| `browser` | browser fallback/cookie tool | cần cài browser bằng Playwright |
| `subtitle` | ROI picker GUI | cài `opencv-python` |
| `translate-local` | dịch local Argos | cài `argos-translate` |
| `all` | cài tất cả extras | phù hợp cho máy dev/agent |

## 2. Lệnh phát triển chung

```bash
make help          # xem danh sách target
make install-dev   # cài editable với dev + server
make install-all   # cài editable với tất cả extras
make test          # chạy toàn bộ pytest
make lint          # ruff check toàn repo
make lint-new      # ruff check các module subtitle/API mới
make check         # lint-new + test
make clean         # dọn cache Python/pytest/ruff
```

Nếu không dùng `make`, lệnh tương đương:

```bash
python -m ruff check .
python -m pytest tests
```

Lưu ý hiện repo có một số lint cũ ngoài phạm vi subtitle; khi chỉ cần kiểm tra phần subtitle/API mới, dùng:

```bash
python -m ruff check subtitle cli/subtitle_commands.py server/subtitle_api.py server/subtitle_jobs.py tests/test_subtitle_*.py
```

## 3. CLI downloader chính

Entry point:

```bash
douyin-dl [options]
# hoặc
python run.py [options]
```

### 3.1 Download bằng URL

```bash
douyin-dl \
  --url "https://www.douyin.com/video/..." \
  --config config.yml \
  --path ./Downloaded \
  --thread 5
```

Có thể truyền nhiều URL bằng cách lặp lại `--url`:

```bash
douyin-dl -u "URL_1" -u "URL_2" -c config.yml
```

Tham số chính:

| Tham số | Ý nghĩa |
| --- | --- |
| `-u`, `--url` | URL Douyin cần tải, có thể lặp nhiều lần |
| `-c`, `--config` | file YAML config, mặc định `config.yml` |
| `-p`, `--path` | thư mục lưu output |
| `-t`, `--thread` | số luồng/concurrency |
| `--verbose` | bật log chi tiết |
| `--show-warnings` | chỉ hiện warning/error |
| `--version` | in version |

### 3.2 Hot board và search

```bash
douyin-dl --hot-board 20 -c config.yml
douyin-dl --search "từ khóa" --search-max 50 -c config.yml
```

| Tham số | Ý nghĩa |
| --- | --- |
| `--hot-board [N]` | lấy bảng hot search, `N` là số dòng tối đa |
| `--search KEYWORD` | tìm video theo keyword |
| `--search-max N` | giới hạn số kết quả search |

## 4. REST API server

Cài extra server:

```bash
python -m pip install -e ".[server]"
```

Chạy server:

```bash
douyin-dl --serve --serve-host 127.0.0.1 --serve-port 8000 -c config.yml
# hoặc
make serve
```

Endpoint chính:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Tạo job download:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/download \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.douyin.com/video/..."}'
```

Poll job:

```bash
curl http://127.0.0.1:8000/api/v1/jobs/JOB_ID
curl http://127.0.0.1:8000/api/v1/jobs
```

## 5. Subtitle CLI

Subtitle pipeline gồm:

```text
SRT gốc → dịch SRT giữ timestamp → ASS style → optional mask → burn video
```

Các lệnh bên dưới không rewrite downloader chính; chúng là subcommand độc lập của `douyin-dl`.

### 5.1 Dịch SRT giữ timestamp

```bash
douyin-dl translate-srt \
  --input input.srt \
  --output input.vi.srt \
  --source-lang zh \
  --target-lang vi \
  --translator noop \
  --batch-size 20
```

| Tham số | Ý nghĩa |
| --- | --- |
| `--input` | file SRT gốc |
| `--output` | file SRT sau dịch |
| `--source-lang` | ngôn ngữ nguồn, mặc định `zh` |
| `--target-lang` | ngôn ngữ đích, mặc định `vi` |
| `--translator` | `noop`, `argos`, hoặc `ollama` |
| `--batch-size` | số cue mỗi batch |
| `--no-preserve-line-breaks` | gộp multiline cue thành 1 dòng trước khi dịch |

Ghi chú:

- `noop` không dịch nội dung, dùng để test flow.
- Mặc định giữ line break trong từng cue.
- Sau dịch có validate cue count và timestamp không đổi.

### 5.2 Convert SRT sang ASS

```bash
douyin-dl srt-to-ass \
  --input input.vi.srt \
  --output input.vi.ass \
  --style-preset douyin_vi \
  --font "Noto Sans" \
  --font-size 42 \
  --alignment 2 \
  --margin-v 70 \
  --outline 2 \
  --shadow 1
```

| Tham số | Ý nghĩa |
| --- | --- |
| `--input` | file SRT đầu vào |
| `--output` | file ASS đầu ra |
| `--style-preset` | preset trong config, mặc định `douyin_vi` |
| `--font` | override font |
| `--font-size` | override cỡ chữ |
| `--alignment` | ASS alignment, `2` là bottom-center |
| `--margin-v` | margin dọc |
| `--outline` | độ dày viền chữ |
| `--shadow` | độ đổ bóng |

### 5.3 Burn ASS vào video

```bash
douyin-dl burn-sub \
  --video input.mp4 \
  --ass input.vi.ass \
  --output output.vi.mp4 \
  --ffmpeg-path ffmpeg \
  --fonts-dir ./fonts \
  --video-codec libx264 \
  --audio-codec copy \
  --crf 18 \
  --preset medium
```

Yêu cầu máy có FFmpeg. Nếu cần font tiếng Việt ổn định, đặt font vào `./fonts` và truyền `--fonts-dir`.

### 5.4 Chọn vùng subtitle cũ bằng ROI picker

```bash
douyin-dl pick-mask-rect \
  --video input.mp4 \
  --timestamp 00:00:03 \
  --output mask_rect.json \
  --ffmpeg-path ffmpeg
```

Output sẽ có dạng:

```text
Selected rect: 0,880,1080,180
Use: --mask-mode blur --mask-rect 0,880,1080,180
Saved: mask_rect.json
```

Nếu môi trường không có GUI/OpenCV, tool sẽ fallback sang frame preview + nhập tọa độ thủ công.

### 5.5 Burn kèm mask subtitle cũ

```bash
douyin-dl burn-sub \
  --video input.mp4 \
  --ass input.vi.ass \
  --output output.vi.mp4 \
  --mask-mode blur \
  --mask-rect 0,880,1080,180 \
  --blur-strength 12
```

| Mode | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `none` | không che subtitle cũ | video chưa có hard-sub |
| `box` | vẽ hộp đen/transparent lên vùng cũ | chắc chắn che được chữ |
| `blur` | blur vùng cũ rồi overlay lại | đẹp hơn box nhưng có thể còn bóng chữ |
| `crop` | cắt từ `rect.y` xuống hết phần dưới video | chỉ dùng khi phần dưới không quan trọng |

### 5.6 Pipeline end-to-end

```bash
douyin-dl subtitle-pipeline \
  --video input.mp4 \
  --srt input.srt \
  --output output.vi.mp4 \
  --output-dir ./subtitle_outputs \
  --source-lang zh \
  --target-lang vi \
  --translator noop \
  --batch-size 20 \
  --style-preset douyin_vi \
  --mask-mode blur \
  --mask-rect 0,880,1080,180 \
  --ffmpeg-path ffmpeg \
  --fonts-dir ./fonts
```

Chỉ dịch và tạo ASS, không burn video:

```bash
douyin-dl subtitle-pipeline \
  --video input.mp4 \
  --srt input.srt \
  --output-dir ./subtitle_outputs \
  --translator noop \
  --no-burn
```

## 6. Subtitle API

Server mode dùng chung `/api/v1/jobs/{job_id}` để poll cả download job và subtitle job.

### 6.1 Translate

```bash
curl -X POST http://127.0.0.1:8000/api/v1/subtitles/translate \
  -H "Content-Type: application/json" \
  -d '{
    "input_srt_path": "input.srt",
    "output_srt_path": "input.vi.srt",
    "source_lang": "zh",
    "target_lang": "vi",
    "translator": "noop",
    "batch_size": 20
  }'
```

### 6.2 Convert ASS

```bash
curl -X POST http://127.0.0.1:8000/api/v1/subtitles/convert-ass \
  -H "Content-Type: application/json" \
  -d '{
    "input_srt_path": "input.vi.srt",
    "output_ass_path": "input.vi.ass",
    "style_preset": "douyin_vi"
  }'
```

### 6.3 Burn

```bash
curl -X POST http://127.0.0.1:8000/api/v1/subtitles/burn \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "input.mp4",
    "ass_path": "input.vi.ass",
    "output_video_path": "output.vi.mp4",
    "mask": {
      "mode": "blur",
      "rect": {"x": 0, "y": 880, "w": 1080, "h": 180},
      "blur_strength": 12
    }
  }'
```

### 6.4 Pipeline

```bash
curl -X POST http://127.0.0.1:8000/api/v1/subtitles/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "input.mp4",
    "input_srt_path": "input.srt",
    "output_dir": "./subtitle_outputs",
    "translator": "noop",
    "style_preset": "douyin_vi",
    "burn": true,
    "mask": {
      "mode": "blur",
      "rect": {"x": 0, "y": 880, "w": 1080, "h": 180}
    }
  }'
```

Poll:

```bash
curl http://127.0.0.1:8000/api/v1/jobs/JOB_ID
```

Job subtitle có thêm:

```json
{
  "stage": "burn",
  "progress": {"current": 4, "total": 5, "message": "Burning ASS into video"},
  "outputs": {
    "translated_srt": "input.vi.srt",
    "ass": "input.vi.ass",
    "video": "output.vi.mp4"
  }
}
```

## 7. Makefile targets cho subtitle

```bash
make subtitle-tests
make subtitle-lint
make subtitle-check
make subtitle-translate INPUT=input.srt OUTPUT=input.vi.srt TRANSLATOR=noop
make subtitle-ass INPUT=input.vi.srt OUTPUT=input.vi.ass
make subtitle-pick VIDEO=input.mp4 TIME=00:00:03 MASK_JSON=mask_rect.json
make subtitle-burn VIDEO=input.mp4 ASS=input.vi.ass OUTPUT=output.vi.mp4 MASK_MODE=blur MASK_RECT=0,880,1080,180
make subtitle-pipeline VIDEO=input.mp4 SRT=input.srt OUTPUT=output.vi.mp4 MASK_MODE=blur MASK_RECT=0,880,1080,180
```

Các biến Makefile hay dùng:

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `CONFIG` | `config.yml` | file config |
| `HOST` | `127.0.0.1` | host API server |
| `PORT` | `8000` | port API server |
| `INPUT` | rỗng | file input cho SRT/ASS |
| `OUTPUT` | rỗng | output file |
| `VIDEO` | rỗng | input video |
| `SRT` | rỗng | input SRT |
| `ASS` | rỗng | input ASS |
| `TRANSLATOR` | `noop` | backend dịch |
| `STYLE` | `douyin_vi` | style preset |
| `MASK_MODE` | `none` | `none/box/blur/crop` |
| `MASK_RECT` | rỗng | tọa độ `x,y,w,h` |
| `FFMPEG` | `ffmpeg` | đường dẫn ffmpeg |
| `FONTS_DIR` | rỗng | thư mục font |

## 8. Checklist cho AI agent trước khi mở PR

1. Đọc docs liên quan trong `docs/vi/`.
2. Không sửa pipeline download chính nếu có thể mở rộng bằng module mới.
3. Nếu thêm feature mới, cập nhật plan/checklist tiếng Việt.
4. Chạy ít nhất:

```bash
make subtitle-check
make test
```

5. Nếu sửa toàn repo hoặc CI yêu cầu:

```bash
make lint
```

6. Tạo PR với phần test rõ ràng, ghi chú nếu `ruff check .` fail do lỗi cũ ngoài phạm vi thay đổi.

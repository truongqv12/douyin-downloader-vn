# Kế hoạch phát triển tính năng Subtitle Pipeline

Tài liệu này là checklist triển khai chính thức cho tính năng xử lý phụ đề/dịch/nhúng subtitle. Mỗi phần làm xong phải đánh dấu ngay để bảo đảm tiến độ bám sát kế hoạch.

## Quy tắc thực hiện

- [x] Không rewrite kiến trúc download hiện tại.
- [x] Core xử lý nằm trong package `subtitle/`.
- [x] CLI/API chỉ là lớp gọi service.
- [x] Mỗi giai đoạn có test tương ứng trước khi chuyển giai đoạn sau.
- [x] Mỗi giai đoạn xong phải cập nhật checklist này.
- [x] Tài liệu tiếng Việt được cập nhật theo tính năng.
- [x] Logic phức tạp có comment ngắn, rõ, không comment lan man.
- [x] API paid chỉ optional, không làm dependency bắt buộc.

## Giai đoạn 1 — Nền tảng đọc/ghi SRT + dịch giữ timestamp

### Mục tiêu

Dịch file SRT sang tiếng Việt nhưng giữ nguyên số thứ tự cue, timestamp start/end, số lượng cue và multiline subtitle.

### Phạm vi

- Thêm core module `subtitle/models.py`, `subtitle/errors.py`, `subtitle/srt_parser.py`, `subtitle/translator.py`.
- Thêm translator backend `noop`, `argos`, `ollama`.
- Thêm CLI `translate-srt`.
- Thêm test parser và translate.

### Checklist

- [x] Tạo model `SubtitleCue`.
- [x] Parse SRT UTF-8/UTF-8-BOM.
- [x] Ghi SRT chuẩn `HH:MM:SS,mmm`.
- [x] Validate cue count/timestamp sau dịch.
- [x] Implement translator `noop` để test không cần API/model.
- [x] Implement backend Argos optional import rõ lỗi.
- [x] Implement backend Ollama local optional.
- [x] CLI `translate-srt` chạy độc lập.
- [x] Test parser multiline/BOM/CRLF.
- [x] Test timestamp không đổi sau dịch.
- [x] Cập nhật tài liệu tiếng Việt cho Giai đoạn 1.

## Giai đoạn 2 — Convert SRT sang ASS với style preset

### Mục tiêu

Tạo ASS từ SRT đã dịch theo preset style ổn định cho video Douyin, có font, outline, shadow và margin.

### Phạm vi

- Thêm `subtitle/style.py`.
- Thêm `subtitle/ass_converter.py`.
- Thêm CLI `srt-to-ass`.
- Thêm config style preset.
- Thêm test ASS converter.

### Checklist

- [x] Tạo style preset model.
- [x] Load style từ config hoặc CLI override.
- [x] Convert cue SRT sang ASS dialogue.
- [x] Escape text ASS: `{}`, `\`, newline.
- [x] Hỗ trợ tiếng Việt UTF-8.
- [x] CLI `srt-to-ass`.
- [x] Test ASS header/style snapshot.
- [x] Test escape ký tự đặc biệt.
- [x] Cập nhật tài liệu tiếng Việt về style preset.

## Giai đoạn 3 — Burn ASS vào video bằng FFmpeg

### Mục tiêu

Hard-burn ASS vào video bằng FFmpeg, chưa mask subtitle cũ.

### Phạm vi

- Thêm `subtitle/ffmpeg.py`.
- Thêm `subtitle/burner.py`.
- Thêm CLI `burn-sub`.
- Thêm test FFmpeg command generation và smoke test nếu có FFmpeg.

### Checklist

- [x] Tìm FFmpeg bằng config/CLI/path system.
- [x] Build command bằng list args, không shell string.
- [x] Escape path trong FFmpeg filter.
- [x] Burn ASS bằng `subtitles=` filter.
- [x] Hỗ trợ `fonts_dir`.
- [x] CLI `burn-sub`.
- [x] Unit test command generation.
- [x] Smoke test FFmpeg nếu binary tồn tại.
- [x] Cập nhật tài liệu tiếng Việt về FFmpeg/font.

## Giai đoạn 4 — Mask subtitle cũ + mini CLI chọn vùng

### Mục tiêu

Không phải đoán tọa độ. Có tool phụ để khoanh vùng subtitle cũ, xuất `mask_rect`, rồi pipeline dùng tọa độ đó.

### Phạm vi

- Thêm `subtitle/mask.py`.
- Thêm `subtitle/video_probe.py`.
- Thêm `subtitle/roi_picker.py`.
- Mở rộng CLI `burn-sub` có mask.
- Thêm CLI `pick-mask-rect`.
- Thêm test mask và coordinate scaling logic.

### Checklist

- [x] Implement `MaskRect` parse/validate.
- [x] Lấy video width/height bằng ffprobe.
- [x] Validate rect nằm trong video bounds.
- [x] Build filter `box`.
- [x] Build filter `blur`.
- [x] Build filter `crop`.
- [x] Tích hợp mask vào `burn-sub`.
- [x] Implement `pick-mask-rect` bằng OpenCV optional.
- [x] Output JSON chứa rect và CLI args.
- [x] Test filter string.
- [x] Test rect validation.
- [x] Test coordinate scaling logic.
- [x] Cập nhật tài liệu tiếng Việt hướng dẫn chọn vùng.

## Giai đoạn 5 — Pipeline end-to-end + API server

### Mục tiêu

Một lệnh/API chạy trọn quy trình: video + SRT → translate → ASS → optional mask → burn → output video.

### Phạm vi

- Thêm `subtitle/result.py`.
- Thêm `subtitle/pipeline.py`.
- Thêm CLI `subtitle-pipeline`.
- Thêm `server/subtitle_jobs.py`.
- Thêm `server/subtitle_api.py`.
- Register subtitle endpoints trong `server/app.py`.
- Thêm config/default và config example.
- Thêm test pipeline và API.

### Checklist

- [x] Implement `SubtitlePipeline` orchestration.
- [x] Pipeline trả `PipelineResult` có outputs/errors/stage.
- [x] CLI `subtitle-pipeline`.
- [x] API endpoint translate.
- [x] API endpoint convert-ass.
- [x] API endpoint burn.
- [x] API endpoint pipeline.
- [x] Subtitle job manager có stage/progress/outputs.
- [x] Không phá `/api/v1/download` hiện tại.
- [x] Test pipeline với fake translator/burner.
- [x] Test API không gọi thật FFmpeg/API ngoài.
- [x] Cập nhật tài liệu tiếng Việt end-to-end.

## Kiểm tra cuối

- [x] `python -m pytest tests/`
- [x] `python -m ruff check subtitle cli/subtitle_commands.py server/subtitle_api.py server/subtitle_jobs.py tests/test_subtitle_*.py`
- [x] Cập nhật README hoặc tài liệu liên quan nếu cần.
- [ ] Tạo PR và kiểm tra CI.

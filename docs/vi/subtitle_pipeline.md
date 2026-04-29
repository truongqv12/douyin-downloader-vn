# Hướng dẫn Subtitle Pipeline

Tính năng subtitle pipeline bổ sung các bước xử lý phụ đề sau khi đã có file SRT:

```text
video + input.srt
→ dịch SRT giữ timestamp
→ convert SRT sang ASS theo style preset
→ tùy chọn che subtitle cũ bằng box/blur/crop
→ burn ASS vào video bằng FFmpeg
```

## 1. Dịch SRT giữ timestamp

```bash
douyin-dl translate-srt \
  --input input.srt \
  --output input.vi.srt \
  --source-lang zh \
  --target-lang vi \
  --translator noop
```

`noop` dùng để test pipeline, không dịch nội dung. Backend local có thể dùng `argos` hoặc `ollama` nếu đã cài/cấu hình.

## 2. Convert SRT sang ASS

```bash
douyin-dl srt-to-ass \
  --input input.vi.srt \
  --output input.vi.ass \
  --style-preset douyin_vi \
  --font "Noto Sans" \
  --font-size 42 \
  --margin-v 70
```

ASS hỗ trợ style tốt hơn SRT: font, outline, shadow, alignment và margin. Nên dùng font có hỗ trợ tiếng Việt như `Noto Sans`, `Arial` hoặc font được mount qua `fonts_dir`.

## 3. Burn ASS vào video

```bash
douyin-dl burn-sub \
  --video input.mp4 \
  --ass input.vi.ass \
  --output output.vi.mp4 \
  --ffmpeg-path ffmpeg \
  --fonts-dir ./fonts
```

Máy cần có FFmpeg. Nếu chạy trong Docker cần image có `ffmpeg` và font tiếng Việt.

## 4. Chọn vùng subtitle cũ để mask

Tool phụ giúp không phải đoán tọa độ:

```bash
douyin-dl pick-mask-rect \
  --video input.mp4 \
  --timestamp 00:00:03 \
  --output mask_rect.json
```

Tool sẽ mở frame video, cho kéo chuột chọn vùng subtitle cũ và in ra:

```text
Use: --mask-mode blur --mask-rect x,y,w,h
```

Nếu môi trường không có GUI/OpenCV, có thể extract preview frame bằng FFmpeg rồi nhập tọa độ thủ công.

## 5. Burn kèm mask subtitle cũ

```bash
douyin-dl burn-sub \
  --video input.mp4 \
  --ass input.vi.ass \
  --output output.vi.mp4 \
  --mask-mode blur \
  --mask-rect 0,880,1080,180
```

Các mode:

- `box`: che chắc chắn nhất nhưng nhìn thô.
- `blur`: tự nhiên hơn nhưng có thể còn thấy chữ cũ.
- `crop`: cắt bỏ vùng subtitle cũ, chỉ hợp khi vùng đó không quan trọng.
- `none`: không che.

## 6. Pipeline end-to-end

```bash
douyin-dl subtitle-pipeline \
  --video input.mp4 \
  --srt input.srt \
  --output output.vi.mp4 \
  --source-lang zh \
  --target-lang vi \
  --translator noop \
  --style-preset douyin_vi \
  --mask-mode blur \
  --mask-rect 0,880,1080,180 \
  --ffmpeg-path ffmpeg \
  --fonts-dir ./fonts
```

Nếu chỉ muốn dịch và tạo ASS, chưa burn video:

```bash
douyin-dl subtitle-pipeline \
  --video input.mp4 \
  --srt input.srt \
  --output-dir ./subtitle_outputs \
  --no-burn
```

## 7. API server

Khi chạy server:

```bash
douyin-dl --serve --serve-port 8000
```

Các endpoint mới:

- `POST /api/v1/subtitles/translate`
- `POST /api/v1/subtitles/convert-ass`
- `POST /api/v1/subtitles/burn`
- `POST /api/v1/subtitles/pipeline`
- `GET /api/v1/jobs/{job_id}`

Ví dụ pipeline:

```json
{
  "video_path": "input.mp4",
  "input_srt_path": "input.srt",
  "output_video_path": "output.vi.mp4",
  "source_lang": "zh",
  "target_lang": "vi",
  "translator": "noop",
  "style_preset": "douyin_vi",
  "mask": {
    "mode": "blur",
    "rect": {"x": 0, "y": 880, "w": 1080, "h": 180}
  },
  "burn": true
}
```

## Lưu ý kỹ thuật

- SRT được đọc bằng `utf-8-sig` để xử lý BOM.
- Dịch chỉ tác động vào text, không cho translator sửa timestamp.
- ASS cần escape ký tự `{}`, `\` và newline để tránh lỗi style.
- FFmpeg filter path cần escape riêng, nhất là Windows path.
- API nhận file path cục bộ; nếu expose server ra ngoài cần giới hạn quyền đọc/ghi theo workspace.

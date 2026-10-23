# Bokin Up Video: ghi chú cho mỗi phiên làm việc

Đọc trước: `README.md`. Hệ thống Bokin (quy tắc chung) nằm ở repo `vhung-spec/bokin-image-to-video-loop`:
`docs/tong-quan-he-thong.md`.

## Repo
- `upvideo/` tool dòng lệnh tải video lên YouTube và hẹn giờ đăng, **không dùng YouTube API**: Chrome thật (patchright),
  mỗi kênh một hồ sơ Chrome đăng nhập tay một lần. `bokin_upvideo.py` (các lệnh), `studio.py` (các bước trong
  YouTube Studio, mọi selector trong `SEL`), `jobs.py` (file lịch CSV, file kết quả).
- `tests/fake_studio.py` Studio giả lập, `tests/test_upvideo.py` bài thử đầu-cuối với Chrome thật.
- `cai-dat-windows.bat`, `cai-dat-linux.sh` cài đặt; `upvideo.bat`, `upvideo.sh` chạy lệnh.
- `.github/workflows/upvideo.yml` chạy selftest và bài thử đầu-cuối trên Windows và Linux.
- Kiểm tra nhanh: `python upvideo/bokin_upvideo.py selftest`; e2e: `python tests/test_upvideo.py` (Linux:
  `xvfb-run -a`). Trên Linux, thư mục tạm phải có đường dẫn ngắn (Chrome không chạy với `--user-data-dir` quá dài).
- `suno/` tool thứ hai, **Bokin Suno** (hướng dẫn: `SUNO.md`): tải các bài trong một workspace Suno về thư mục, cũng
  bằng Chrome thật (mỗi tài khoản Suno một hồ sơ, dữ liệu ở `data/suno/`). `bokin_suno.py` (các lệnh), `web.py` (các
  bước trên suno.com, mọi selector và chữ trên nút trong `SEL`), `folder.py` (tên file, `danh-sach.csv`).
  `tests/fake_suno.py` Suno giả lập, `tests/test_suno.py`, `.github/workflows/suno.yml`; `suno.bat`, `suno.sh`.
  Kiểm tra nhanh: `python suno/bokin_suno.py selftest`; e2e: `python tests/test_suno.py`.

## Quy tắc
- Trả lời chủ dự án bằng **tiếng Việt**, đơn giản, từng bước. Mã và chú thích trong mã bằng tiếng Anh.
- Không commit hồ sơ Chrome, cookie, mật khẩu, email thật, ID kênh thật, IP. Thư mục `data/` không bao giờ vào git.
  Nhắc chủ che tên kênh/email trong ảnh chụp màn hình.
- Tool chỉ **hẹn giờ** (Schedule); không bao giờ bấm đăng nếu ngày giờ chưa được kiểm tra lại đúng. Lỗi giữa chừng thì
  để video ở dạng nháp riêng tư.
- Ảnh lỗi chỉ lưu hộp tải lên (`ytcp-uploads-dialog`), không lưu cả trang (trang Studio chứa dữ liệu phiên).
- Studio giả lập phải đi cùng `SEL`: sửa selector thì sửa cả Studio giả lập và bài thử.
- Suno: chỉ tải qua nút Download của Suno (tính lượt tải như tải tay). Không lấy file bằng đường khác để né giới hạn
  lượt tải của gói, không bao giờ bấm Buy/Upgrade; hết lượt thì dừng. Suno giả lập đi cùng `SEL` như Studio giả lập.
  Ảnh lỗi: cửa sổ, menu và hộp thoại đang mở, nhãn các nút; không lưu cả trang. Chưa thử trên suno.com thật: máy chủ
  phiên làm việc không vào được suno.com; sửa `SEL` theo ảnh và file `.html` chủ gửi.
- Không tạo pull request nếu chủ không yêu cầu. Kiểm chứng trên Windows và Linux (CI) trước khi báo xong.

# Bokin Up Video: tải video lên YouTube và hẹn giờ đăng

Tool chạy trên VPS hoặc máy tính bất kỳ (**Windows** hoặc **Linux**). Nó tải video lên các kênh YouTube của công ty
và **hẹn giờ đăng** (video tự công khai đúng giờ đã đặt). Mỗi máy dùng cho vài kênh (ví dụ 3–4 kênh).

Tool **không dùng YouTube API**. Nó mở một Chrome thật, đã đăng nhập sẵn kênh, rồi làm đúng các bước một người làm
trong YouTube Studio: chọn file, điền tiêu đề và mô tả, chọn **Schedule**, điền ngày giờ, bấm **Schedule**.
Vì vậy không cần tạo dự án Google hay chờ Google duyệt, và video không bị khoá ở chế độ Riêng tư.

## Cần biết trước

- **Mỗi kênh đăng nhập bằng tay một lần**, ngay trên máy sẽ chạy tool. Tool **không lưu mật khẩu**. Nó giữ phiên
  đăng nhập trong hồ sơ Chrome riêng của từng kênh (`data/profiles/<tên kênh>`).
  - Không chép thư mục `data` sang máy khác và không gửi nó cho ai: ai có nó là vào được kênh.
  - Máy khác thì đăng nhập lại trên máy đó.
- **YouTube Studio của kênh phải để tiếng Anh**: Studio → ảnh đại diện (góc trên phải) → **Language** →
  **English (US)**. Đây là cài đặt của tài khoản Google, đặt một lần. Nếu Studio không ở tiếng Anh, tool dừng lại
  và báo, không tải gì lên.
- **Giờ đăng tính theo giờ Việt Nam.** Muốn múi giờ khác (ví dụ giờ Mỹ), xem mục *Múi giờ* bên dưới.
- **Tool tự động hoá giao diện YouTube.** Khi YouTube đổi giao diện Studio, tool có thể ngừng chạy cho tới khi được
  sửa. Lúc đó tool báo lỗi và chụp màn hình.
  - Video **không bao giờ** bị đăng sai giờ: tool chỉ bấm **Schedule** sau khi đã điền đúng ngày giờ và kiểm tra lại.
  - Nếu tool dừng giữa chừng, video nằm ở dạng **nháp riêng tư** trong Studio (mục Content). Vào xoá bằng tay.
- Điều khoản YouTube không cho phép truy cập bằng công cụ tự động. Dùng ở mức vừa phải như người thật (mỗi kênh vài
  video mỗi ngày) thì ít rủi ro, nhưng **không phải không có**. YouTube cũng giới hạn số video tải lên mỗi ngày của
  mỗi kênh.
- Trước khi dùng thật, **thử với một video ngắn**. Xem trong Studio rằng ngày giờ hẹn đúng.

## Cài đặt trên Windows (VPS hoặc máy tính)

1. Cài **Python 3.10 trở lên** từ <https://www.python.org/downloads/>. Khi cài, tick **Add python.exe to PATH**.
2. Tải repo này về máy (nút **Code → Download ZIP** trên GitHub), giải nén ra một thư mục, ví dụ `C:\BokinUpVideo`.
3. Bấm đúp **`cai-dat-windows.bat`**. Nó cài các thư viện cần thiết, cài Google Chrome nếu máy chưa có, rồi tự kiểm
   tra. Cuối cùng phải hiện `selftest OK` và `Xong`.

Các lệnh bên dưới gõ trong cửa sổ dòng lệnh mở **trong thư mục của tool**. Cách mở: vào thư mục trong File Explorer,
gõ `cmd` vào thanh địa chỉ rồi Enter. Trên Windows, lệnh bắt đầu bằng **`upvideo`**.

## Cài đặt trên Linux (Ubuntu/Debian)

1. Chép repo vào máy, ví dụ bằng `git clone`.
2. Trong thư mục repo, chạy:
   ```
   bash cai-dat-linux.sh
   ```
   Nó cài Python venv, thư viện, Google Chrome và màn hình ảo (`xvfb`), rồi tự kiểm tra.
3. **Đăng nhập kênh cần màn hình thật**, vì phải gõ mật khẩu Google. Cài màn hình từ xa cho VPS một lần, rồi vào
   bằng **Remote Desktop** (có sẵn trên Windows):
   ```
   sudo apt install -y xfce4 xrdp
   echo xfce4-session > ~/.xsession
   sudo systemctl restart xrdp
   ```
   Nên dùng một tài khoản Linux thường, không dùng `root`.
   - Lệnh `login`: chạy trong Remote Desktop.
   - Các lệnh khác: chạy qua SSH cũng được. `upvideo.sh` tự tạo màn hình ảo cho Chrome.

Trên Linux, lệnh bắt đầu bằng **`./upvideo.sh`** thay cho `upvideo`.

## Đăng nhập một kênh (mỗi kênh một lần)

Đặt cho mỗi kênh một **tên ngắn**: chữ không dấu, số, `-` hoặc `_`. Ví dụ `anime1`, `jazz1`.

```
upvideo login anime1
```

Một cửa sổ Chrome mở ra:

1. Đăng nhập **Gmail của kênh**, làm cả bước xác minh 2 lớp nếu Google hỏi.
2. Khi đã vào YouTube Studio, kiểm tra Studio **đang mở đúng kênh**. Nếu Gmail có nhiều kênh, bấm ảnh đại diện →
   **Switch account** để đổi.
3. **Đóng cửa sổ Chrome.**

Tool báo `Đã lưu kênh anime1 (UC...)`. Làm lại cho từng kênh khác.

- `upvideo channels`: xem các kênh đã đăng nhập.
- `upvideo check`: kiểm tra các kênh còn đăng nhập không. Nếu Google đăng xuất kênh (đổi mật khẩu…), chạy lại
  `upvideo login <tên>`.

## Hẹn giờ đăng một video

```
upvideo upload anime1 "D:\Video\lofi.mp4" --title "Lofi mưa đêm 10 giờ" --at "2026-11-01 20:00" --description-file "D:\Video\mo-ta.txt"
```

- `--at`: giờ đăng, dạng `2026-11-01 20:00` hoặc `01/11/2026 20:00` (ngày trước tháng).
  Phải sau lúc chạy lệnh **ít nhất 15 phút**.
- Mô tả: dùng `--description "..."` hoặc `--description-file <file .txt>`. Bỏ trống thì YouTube dùng mô tả mặc định
  của kênh (Studio → Settings → Upload defaults).

Tool tải video lên (video dài thì mất lâu, chờ đến khi xong), đặt giờ rồi bấm **Schedule**. Cuối cùng nó in link video.

## Hẹn giờ nhiều video: file lịch

Tạo file lịch bằng Excel, mỗi dòng một video. Xem mẫu: `vi-du/lich-dang.csv`.

| kenh | video | tieu_de | mo_ta | gio_dang |
|---|---|---|---|---|
| anime1 | D:\Video\lofi-mua-dem.mp4 | Lofi mưa đêm 10 giờ | @mo-ta-mau.txt | 2026-11-01 20:00 |
| anime1 | D:\Video\lofi-buoi-sang.mp4 | Lofi buổi sáng 3 giờ | | 02/11/2026 07:30 |

- **kenh**: tên kênh đã `login`.
- **video**: đường dẫn file. Có thể chỉ ghi tên file nếu video nằm cùng thư mục với file lịch.
- **tieu_de**: tối đa 100 ký tự, không có `<` hoặc `>`.
- **mo_ta** (có thể bỏ trống): gõ thẳng nội dung, hoặc `@ten-file.txt` để lấy từ một file chữ.
- **gio_dang**: như `--at` ở trên.
  - Trong Excel, nên đặt cột này dạng **Text**, để Excel không tự đổi sang kiểu tháng/ngày.
  - Dòng tiêu đề viết có dấu cũng được (`Kênh`, `Tiêu đề`, `Giờ đăng`…).
- Lưu file: **File → Save As → CSV UTF-8 (Comma delimited)**. Lưu kiểu CSV thường thì tiếng Việt bị lỗi, tool sẽ báo.

Chạy:

```
upvideo run "D:\Video\lich-dang.csv"
```

- Tool làm lần lượt từng dòng. Dòng lỗi (thiếu file, giờ đã qua, kênh chưa đăng nhập…) được bỏ qua, các dòng khác
  vẫn chạy.
- Kết quả ghi vào file **`lich-dang.ketqua.csv`** cạnh file lịch, gồm trạng thái `xong` / `loi` / `dang_tai`, link
  video và lý do lỗi.
- **Chạy lại cùng file lịch thì an toàn**: dòng đã `xong` không tải lại, chỉ các dòng lỗi được thử lại. Nhờ vậy có thể
  thêm dòng mới vào file rồi chạy lại.
- Dòng `dang_tai` nghĩa là tool bị ngắt đúng lúc bấm Schedule (mất điện, tắt máy…). Mở Studio xem video đã được hẹn
  giờ chưa. Muốn tải lại thì xoá dòng đó trong file kết quả.

## Múi giờ

Mặc định giờ đăng là **giờ Việt Nam** (`Asia/Ho_Chi_Minh`), kể cả khi VPS đặt múi giờ khác. Đổi múi giờ theo một
trong hai cách:

- Cho một lần chạy: thêm `--timezone America/New_York` vào lệnh.
- Mặc định của máy: tạo file `data/settings.json` với nội dung:
  ```json
  {"timezone": "America/New_York"}
  ```

## Khi có lỗi

- Mỗi lỗi có một dòng giải thích bằng tiếng Việt.
- Nhật ký đầy đủ nằm ở `data/logs/upvideo.log`.
- Lỗi trong YouTube Studio có kèm ảnh chụp màn hình `data/logs/loi-<thời gian>-<kênh>.png`.
- Khi gửi ảnh cho người sửa tool, **che tên kênh, email và mọi thông tin riêng**.
- Chạy kèm `--headless` để Chrome không hiện cửa sổ. Mặc định cửa sổ có hiện, để xem tool đang làm gì; đừng bấm vào
  cửa sổ đó khi tool đang chạy.

| Báo lỗi | Cách xử lý |
|---|---|
| Kênh chưa đăng nhập hoặc đã bị đăng xuất | `upvideo login <tên>` |
| Studio đang dùng ngôn ngữ 'vi' | Đặt Studio sang English (US), xem *Cần biết trước* |
| Tài khoản không mở được kênh (Studio chuyển sang kênh khác) | `upvideo login <tên>`, nhớ mở đúng kênh rồi mới đóng Chrome |
| Tải lên đứng yên quá 30 phút | Kiểm tra mạng của VPS; xoá bản nháp trong Studio rồi chạy lại |
| Không thấy ô… / nút Next bị khoá | YouTube đổi giao diện hoặc cần trả lời thêm câu hỏi: xem ảnh chụp màn hình |
| Hồ sơ Chrome đang mở ở cửa sổ khác | Đóng cửa sổ Chrome của tool (hoặc chờ lần chạy kia xong) |

## Cho người phát triển

- Mã nguồn:
  - `upvideo/bokin_upvideo.py`: các lệnh.
  - `upvideo/studio.py`: các bước trong YouTube Studio. Mọi selector nằm trong `SEL`.
  - `upvideo/jobs.py`: file lịch và file kết quả.
- Tự kiểm tra: `python upvideo/bokin_upvideo.py selftest`.
- Thử đầu-cuối với **Studio giả lập** (`tests/fake_studio.py`) bằng Chrome thật:
  - `python tests/test_upvideo.py [--headless]`
  - Linux không có màn hình: `xvfb-run -a python tests/test_upvideo.py`
- GitHub Actions (`.github/workflows/upvideo.yml`) chạy cả hai bài thử trên Windows và Linux mỗi lần push.
- Studio giả lập không phải YouTube thật. Khi YouTube đổi giao diện, phải sửa `SEL` trong `studio.py` theo ảnh chụp
  và file `.html` của hộp tải lên trong `data/logs`, rồi sửa Studio giả lập cho giống.

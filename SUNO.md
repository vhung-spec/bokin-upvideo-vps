# Bokin Suno: tải nhạc đã làm trên Suno về máy

Tool tải **các bài nhạc trong một workspace Suno** về một thư mục trên máy, dạng **WAV** (hoặc MP3). Chạy lại thì
chỉ tải các bài mới. Tool chạy trên **Windows** hoặc **Linux**, nằm chung thư mục với Bokin Up Video.

Tool **không dùng API**. Nó mở một Chrome thật đã đăng nhập Suno rồi làm đúng các bước một người làm: mở workspace,
rồi với từng bài bấm **⋯ → Download → WAV Audio → Download File**.

## Cần biết trước

- **Mỗi tài khoản Suno đăng nhập bằng tay một lần**, ngay trên máy chạy tool. Tool **không lưu mật khẩu**. Phiên
  đăng nhập nằm trong hồ sơ Chrome riêng của tài khoản (`data/suno/profiles/<tên>`).
  - Không chép thư mục `data` sang máy khác và không gửi nó cho ai: ai có nó là vào được tài khoản Suno.
- **Lượt tải của gói Suno.** Từ 3/9/2026 Suno giới hạn số bài tải mỗi tháng theo gói (gói Pro 20 bài, Premier 60
  bài; gói cao nhất không giới hạn). Tool tải qua **đúng nút Download của Suno**, nên mỗi bài được tính như khi tải
  bằng tay:
  - Một bài tính **1 lượt**, dù tải WAV hay MP3. Tải lại bài đã tải không tính thêm.
  - Khi Suno báo hết lượt, tool **dừng lại**. Tool **không bao giờ bấm mua thêm**.
- **Điều khoản của Suno không cho phép dùng công cụ tự động** trên trang. Tool đi chậm như người (mỗi bài vài
  giây). Dù vậy, rủi ro tài khoản bị nhắc nhở hoặc khoá **vẫn có**. Nên tải vừa phải.
- **Tool chưa được thử trên suno.com thật.** Máy dùng để viết tool không vào được suno.com, nên tool được viết theo
  giao diện Suno đã biết và thử trên một trang Suno giả lập. **Lần chạy đầu có thể cần sửa tool.**
  - Khi gặp lỗi, tool chụp màn hình và lưu một file `.html` trong `data/suno/logs`.
  - Gửi hai file đó cho người sửa tool. Trước khi gửi, **che tên tài khoản và email** trong ảnh.
  - Suno đổi giao diện về sau cũng vậy: tool báo lỗi và chụp màn hình, không làm gì sai trên tài khoản.

## Cài đặt

- **Đã cài Bokin Up Video** (đã chạy `cai-dat-windows.bat`): tải bản mới của repo này về chép đè lên thư mục cũ, rồi
  bấm đúp `cai-dat-windows.bat` một lần nữa. Cuối cùng phải hiện hai dòng `selftest OK` và `Xong`.
- **Chưa cài**: làm theo phần *Cài đặt trên Windows* (hoặc Linux) trong [README.md](README.md).

Các lệnh bên dưới gõ trong cửa sổ dòng lệnh mở **trong thư mục của tool** (trong File Explorer: gõ `cmd` vào thanh địa
chỉ rồi Enter). Trên Windows, lệnh bắt đầu bằng **`suno`**. Trên Linux, dùng **`./suno.sh`** thay cho `suno`.

## Bước 1: đăng nhập Suno (mỗi tài khoản một lần)

Đặt cho tài khoản một **tên ngắn**: chữ không dấu, số, `-` hoặc `_`. Ví dụ `suno1`.

```
suno login suno1
```

Một cửa sổ Chrome mở trang suno.com:

1. Bấm **Sign In**, đăng nhập như mọi khi (Google…), làm cả bước xác minh nếu được hỏi.
2. Khi đã vào Suno (thấy ảnh đại diện của bạn), **đóng cửa sổ Chrome**.

Tool báo `Đã lưu tài khoản suno1`.

- `suno accounts`: xem các tài khoản đã đăng nhập.
- `suno check`: kiểm tra các tài khoản còn đăng nhập không. Bị đăng xuất thì chạy lại `suno login <tên>`.
- `suno remove <tên>`: xoá tài khoản khỏi máy này.

Trên Linux (VPS), lệnh `login` phải chạy trong **Remote Desktop**, như hướng dẫn trong README.

## Bước 2: lấy link của workspace

1. Mở Suno bằng Chrome thường của bạn, mở **workspace** muốn tải.
2. Bấm vào thanh địa chỉ, **Ctrl+C** để chép link. Link có dạng `https://suno.com/create?wid=...`.
3. Thử dán link đó vào một tab mới: phải mở ra **đúng workspace** với đúng các bài. Nếu không, tool cũng không thấy.

Dùng link một **playlist** hoặc link **một bài** cũng được.

## Bước 3: xem trước, rồi tải

Xem workspace có những bài nào (chưa tải gì):

```
suno list suno1 "https://suno.com/create?wid=..."
```

Lần đầu, **tải thử 2 bài**:

```
suno download suno1 "https://suno.com/create?wid=..." --out "D:\Nhac\Suno" --limit 2
```

Mở thư mục `D:\Nhac\Suno`, nghe thử. Đúng rồi thì tải hết (bỏ `--limit 2`):

```
suno download suno1 "https://suno.com/create?wid=..." --out "D:\Nhac\Suno"
```

- Link luôn để trong **ngoặc kép**.
- `--out`: thư mục lưu nhạc. Bỏ trống thì lưu vào thư mục `nhac-suno` cạnh tool.
- Mặc định tải **WAV**. Muốn MP3: thêm `--format mp3`.
- Tên file là tên bài: `Mưa đêm.wav`. Suno tạo bài theo cặp cùng tên, nên bài thứ hai là `Mưa đêm (2).wav`.
- Bài đang tạo dở hoặc bị lỗi trên Suno thì được bỏ qua và báo lỗi; lần chạy sau tool thử lại.
- Nhạc tải về dùng thẳng trong **Bokin Studio Music** (thêm cả thư mục vào danh sách nhạc).

### File danh-sach.csv

Trong thư mục nhạc có file **`danh-sach.csv`** (mở bằng Excel): mỗi bài đã tải một dòng, gồm tên bài, tên file, link
bài trên Suno và lúc tải.

- **Chạy lại cùng lệnh thì chỉ tải bài mới.** Bài đã có trong `danh-sach.csv` không tải lại, **kể cả khi bạn đã xoá
  file nhạc**.
- Muốn tải lại một bài: xoá dòng của bài đó trong `danh-sach.csv`, lưu lại dạng **CSV UTF-8**, rồi chạy lại.
- **Đóng `danh-sach.csv` trong Excel** trước khi chạy tool.
- Mỗi workspace nên tải vào một thư mục riêng cho dễ tìm. Chung một thư mục cũng không sao.

## Tự tải bài mới mỗi ngày (tuỳ chọn)

Trên Windows:

1. Tạo file `tai-nhac-suno.bat` (bằng Notepad) với nội dung như sau, sửa đường dẫn và link cho đúng:
   ```
   @echo off
   cd /d C:\BokinUpVideo
   call suno.bat download suno1 "https://suno.com/create?wid=..." --out "D:\Nhac\Suno"
   ```
2. Mở **Task Scheduler** → **Create Basic Task** → đặt tên → **Daily** → chọn giờ → **Start a program** → chọn file
   `tai-nhac-suno.bat` → **Finish**.
3. Lúc đến giờ, máy phải đang bật và đã đăng nhập Windows.

Trên Linux: thêm lệnh `./suno.sh download ...` vào `crontab -e` (tool tự tạo màn hình ảo cho Chrome).

## Khi có lỗi

- Mỗi lỗi có một dòng giải thích bằng tiếng Việt.
- Nhật ký đầy đủ: `data/suno/logs/suno.log`.
- Lỗi trên trang Suno có kèm ảnh `data/suno/logs/loi-<thời gian>-<tài khoản>.png` và file `.html` cùng tên.
- Chạy kèm `--headless` để Chrome không hiện cửa sổ. Mặc định cửa sổ có hiện để xem tool đang làm gì; đừng bấm vào
  cửa sổ đó khi tool đang chạy.

| Báo lỗi | Cách xử lý |
|---|---|
| Tài khoản Suno chưa đăng nhập hoặc đã bị đăng xuất | `suno login <tên>` |
| Chrome đang đăng nhập một tài khoản Suno khác | `suno login <tên>`, đăng nhập đúng tài khoản |
| Không phải link của Suno | Chép lại link trên thanh địa chỉ, xem *Bước 2* |
| Không thấy bài nào ở link này | Dán link vào Chrome thường xem có mở đúng workspace không |
| Suno chưa cho tải bài này | Bài chưa tạo xong hoặc lỗi trên Suno; lần chạy sau tool thử lại |
| Suno báo hết lượt tải của gói | Chờ sang tháng mới của gói (hoặc tự mua thêm lượt trên Suno), rồi chạy lại |
| 3 bài liền nhau không tải được | Có thể Suno đã đổi giao diện: gửi ảnh và file `.html` trong `data/suno/logs` |
| Không ghi được danh-sach.csv | Đóng file đó trong Excel rồi chạy lại |
| Hồ sơ Chrome đang mở ở cửa sổ khác | Đóng cửa sổ Chrome của tool (hoặc chờ lần chạy kia xong) |

## Cho người phát triển

- Mã nguồn:
  - `suno/bokin_suno.py`: các lệnh.
  - `suno/web.py`: các bước trên suno.com. Mọi selector và chữ trên nút nằm trong `SEL`.
  - `suno/folder.py`: thư mục nhạc, tên file, `danh-sach.csv`.
- Tự kiểm tra: `python suno/bokin_suno.py selftest`.
- Thử đầu-cuối với **Suno giả lập** (`tests/fake_suno.py`) bằng Chrome thật:
  - `python tests/test_suno.py [--headless]`
  - Linux không có màn hình: `xvfb-run -a python tests/test_suno.py`
- GitHub Actions (`.github/workflows/suno.yml`) chạy cả hai bài thử trên Windows và Linux mỗi lần push.
- Suno giả lập không phải Suno thật. Khi Suno đổi giao diện, sửa `SEL` trong `web.py` theo ảnh chụp và file `.html`
  trong `data/suno/logs`, rồi sửa Suno giả lập cho giống.

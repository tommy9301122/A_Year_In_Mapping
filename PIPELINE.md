# AYIM osu! dashboard 資料流程

此流程產生與舊 notebook 相同欄位的難度表、圖集表，供既有 Looker Studio dashboard 匯入。已解析連結並確認 dashboard 標題為 A Year In Mapping 2025，但本次環境無法檢視圖表與資料源設定。因此相容性依原 notebook 的 CSV schema 核對；尚未驗證 dashboard 的計算欄位或連線設定。

## 本次結果：2026-01-01 至 2026-10-23

| 指標 | 結果 |
| --- | ---: |
| 難度 | 22,217 |
| 不重複圖集 | 6,004 |
| 圖集 × 模式列數 | 6,140 |
| 圖集主創 | 1,898 |
| 難度主要作者 | 2,844 |
| 2026 新主創 | 343 |
| 新人身分未知 | 3 |
| 未回傳主創個人資料 | 9 人 |
| 未回傳難度作者個人資料 | 21 人 |

以 UTC `approved_date` 計，本次納入的最早時間為 2026-01-01 00:42:23，最晚為 2026-10-23 11:43:47。來源回應擷取於台北時間 2026-10-23 23:15 至 23:40 之間；日期清單本身在 23:16 取得。10 月 23 日 UTC 尚未結束，並非當日最終版。

9 項回歸測試通過；整理版 notebook 已完整執行並保留結果，使用快取重跑約 19 秒。與原分類對照相比，9,027 個難度的曲風、89 個難度的語言獲得修正。作者查詢由逐張 22,217 次降為 445 批；前兩年資料另外證明 1,314 位主創已有舊作，剩餘 584 位才逐人查完整歷史。詳細機器可讀統計與檔案雜湊見輸出目錄的 `manifest.json`。

## 憑證

原 notebook 的三個值已抽出至本機 `.env`：

| 設定名稱 | 原本用途 |
| --- | --- |
| `OSU_API_KEY` | 原 `osu.ppy.sh/api/get_beatmaps?k=...` 的 API v1 key |
| `OSU_CLIENT_ID` | 原 `osu_client_id`，OAuth client ID |
| `OSU_CLIENT_SECRET` | 原 `osu_client_secret`，OAuth client secret |

程式優先讀取環境變數，其次讀取此目錄 `.env`。`.gitignore` 排除憑證、快取與輸出。不要公開 `.env`；`.env.example` 可供分享。OAuth access token 只留在執行中的記憶體，不寫入 CSV、快取或紀錄。兩份 notebook 均已移除完整憑證與舊執行輸出。

## 執行

在此目錄執行：

```powershell
python -m pip install -r requirements.txt
python ayim_pipeline.py --start 2026-01-01 --end 2026-10-23
```

或直接開啟 `ayim_2026.ipynb` 從上往下執行。核心邏輯集中在 `ayim_pipeline.py`，notebook 僅保留參數、呼叫及資料預覽。舊版流程另存為 `ayim_2026.original_sanitized.ipynb`，憑證已替換為標記、outputs 已清除，不可直接當成可執行版本。

每個成功 API 回應會立即儲存於 `.cache/responses.sqlite3`，預設重用 24 小時內的快取。中斷時重新執行相同命令可續跑；要更新當天新增圖譜和計數，請加 `--refresh`（會重新抓全部資料）。不要同時跑多份 pipeline，因為 API 限速由單一執行程序管理。

```powershell
python ayim_pipeline.py --start 2026-01-01 --end 2026-10-23 --refresh
python -m unittest -v test_ayim_pipeline.py
```

## 修正的資料問題

| 原流程 | 修正 |
| --- | --- |
| `approved_date <= '2026-10-23'` 的字串比較排除結束日時間 | 明確使用 `[開始日 00:00:00, 結束日隔天 00:00:00)`，UTC |
| 分頁只保留年月日，可能重抓同一天甚至停不下來 | 保留秒級游標，重疊一秒、依 beatmap ID 去重；時間戳飽和或沒有前進時明確報錯 |
| `new_mapper` 仍硬寫 2025，且只檢查前 100 個圖集 | 依參數年份判斷；確定出道年份前完整分頁，不假定 API 排序 |
| 每個查詢重新建立 `Ossapi` | 共用一個 HTTP Session 和 OAuth token，到期自動更新 |
| 每張難度逐一查作者、每位作者逐一查國籍 | 作者資料每次 50 張難度、使用者資料每次 50 人 |
| 1898 位主創逐人查完整歷史 | 先用前兩年 Ranked 清單證明已有作品，其餘主創才查完整歷史；查不到不視為新人 |
| Genre 從 Hip Hop 起對照錯位 | 使用正確 ID：9 Hip Hop、10 Electronic、11 Metal、12 Classical、13 Folk、14 Jazz；8 並非有效類別 |
| `FrenchItalian`、Polish ID 錯誤、缺 Italian | 7 French、11 Italian、13 Polish |
| Unicode 只補 null，不補空字串 | 兩者都用英文 title／artist 補值 |
| 只從 GD 作者名單補圖集主創資料 | 以「圖集主創 ∪ 難度作者」查使用者，主創未製作任何難度時也能補齊 |
| 沒有 timeout／重試，bare except 將錯誤當缺值 | timeout、429／5xx 退避重試；429 至少等待 60 秒並遵守 Retry-After，404 使用者保留未知 |
| 全域忽略 warning、切片賦值 | 明確 copy、集中向量化清理，不隱藏 warning |
| 輸出名稱仍為 2021／2025 | 日期區間自動產生檔名及獨立目錄 |

## 資料定義與限制

- **納入範圍**：原生四模式、狀態 Ranked（`1`）與 Loved（`4`），依 API v1 `approved_date` 篩選；與原 dashboard 範圍一致，不含 Qualified／Pending，也不額外加入轉換譜。
- **日期**：API v1 的日期為 UTC。2026-01-01 至 2026-10-23 指 UTC 的這些日曆日期，並非台北時間。最後一天尚未結束時，只能取得執行時已公布資料。
- **new_mapper／is_new**：主創第一次擁有 Ranked／Approved 圖集的年份為指定年，跨所有模式合併判斷。只製作過 GD 或只有 Loved 的人，不因此成為 Ranked 新人。此定義沿用原 notebook 的主創口徑，修正年份與分頁；難度表 `is_new` 也是**圖集主創**的分類，不是每位 GD 作者的出道年份。
- **主創與難度作者**：難度表 `creator_id` 是圖集主創，`gder_id` 是 API v2 beatmap 的主要 `user_id`；`gd = creator_id != gder_id`。現行 API 可有多位 owners，本輸出維持單一主要作者以相容既有 schema，不拆成多列。
- **表粒度**：難度表每個 beatmap ID 一列；圖集表每個 `(beatmapset_id, mode)` 一列。多模式圖集在圖集表有多列，圖集數應使用 `COUNT_DISTINCT(beatmapset_id)`。
- **計數**：playcount／favourite_count 是抓取時累計值，不是歷史結束日快照。playcount 按難度加總到各模式；收藏數是圖集層級，跨模式重複，不能直接將圖集表全部列的收藏數相加。
- **缺值**：被刪除或受限制帳號可能沒有姓名／國籍／出道資料，保留空值，不猜測。其他請求錯誤不吞掉。
- **一致性**：API 不提供跨請求的交易快照。manifest 記錄各來源回應時間範圍；圖譜歷史以目前仍可查詢到的 Ranked 資料為準。

## 輸出與檢查

結果存於 `outputs/2026-01-01_2026-10-23/`：

- `ayim2026_gd_20260101_20261023.csv`：難度表，原 schema 19 欄。
- `ayim2026_20260101_20261023.csv`：圖集表，原 schema 15 欄。
- `ayim_raw_20260101_20261023.csv`：原 API 欄位加整理及作者資料，供追查。
- `source_beatmaps.json`：本次日期範圍原始 API v1 回應（去重及篩選後）。
- `mapper_new_status.json`：每位主創的新 mapper 判定。
- `manifest.json`：擷取時間、列數、缺值統計、輸出 SHA-256、API 請求數與驗證狀態。

CSV 使用 UTF-8 BOM、保留原欄名，布林值輸出 True／False；缺值為空。匯入 dashboard 時替換對應資料源即可。程式在寫 CSV 前檢查：難度 ID 不重複、圖集×模式不重複、日期不越界、分類非空、難度總數與 playcount 能對帳，以及每組圖集的主創／曲名／類別等 metadata 一致。

## 官方參考

- [API v1 文件](https://github.com/ppy/osu-api/wiki)：日期 UTC、`since`、所有模式、limit 500、genre／language ID。
- [API v2 Get Beatmaps](https://osu.ppy.sh/docs/index.html#get-beatmaps)：每次最多 50 張難度。
- [API v2 Get Users](https://osu.ppy.sh/docs/index.html#get-users)：每次最多 50 位使用者。
- [API v2 Get User Beatmaps](https://osu.ppy.sh/docs/index.html#get-user-beatmaps)：Ranked 圖集歷史，limit／offset 分頁。
- [API 使用規範](https://osu.ppy.sh/docs/index.html#terms-of-use)：快取、退避與建議每分鐘不超過 60 次。本流程每次網路請求至少間隔 1.05 秒；使用者批次依 ID 計費配額，另以至少 3 秒間隔處理，避免批次 50 人仍超額。
- [UsersController 官方程式](https://github.com/ppy/osu-web/blob/master/app/Http/Controllers/UsersController.php) 與 [限流 middleware](https://github.com/ppy/osu-web/blob/master/app/Http/Middleware/ThrottleRequests.php)：使用者批次查詢的配額與伺服器端限流實作。

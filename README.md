# A Year In Mapping 2026

osu! 年度創作回顧網站：一次性擷取、Python 整理、自己的唯讀後端及響應式前端。不需要 Google Sheets、Looker Studio 或資料排程。

[公開網站](https://osu-ayim.com/)

包含總覽、曲風／語言、Mapper／Country、Favourite／Playcount、熱門歌曲／藝人及 GD／Host。支援四模式、Ranked／Loved、主創國家、新主創、文字搜尋、分享篩選網址及展開排行。

## 本機啟動

需要 Node.js 20+ 與 Python 3.10+。前後端無 npm 套件依賴。

```sh
python -m pip install -r requirements.txt
npm run dev
# http://127.0.0.1:4173
```

包含真正取得的 **2026-01-01 至 2026-10-23 預覽快照**：22,217 個難度、6,004 個不重複圖集。網站預設 osu!standard + Ranked，數字隨篩選改變。此快照不是全年數據，10/23 也尚未結束，頁面有明確標記。

## 年底一次性發佈

日期採 UTC。完整年度需在 **2027-01-01 00:00 UTC（台北 08:00）之後**執行。12/31 當天擷取只能作為截至當時的預覽。收藏與遊玩是抓取時累計值，API 無法還原精確的歷史年底計數。

複製 `.env.example` 為 `.env`，填入 API v1 key、OAuth client ID／secret。不要提交 `.env`。新版 pipeline 沿用前次 session 的快取、限速、分頁及新人判定修正。

```sh
python ayim_pipeline.py --start 2026-01-01 --end 2026-12-31 --refresh
python scripts/export_snapshot.py outputs/2026-01-01_2026-12-31 --final
python -m unittest -v test_ayim_pipeline.py
npm test
npm run build
```

再手動部署新版本。`--final` 檢查完整日期範圍、所有來源回應在年末之後、CSV SHA-256 與統計一致性，未通過便停止。預覽時省略 `--final`。`--refresh` 避免沿用年度未結束前的回應。

快照變更應連同程式提交至 GitHub。資料更新與部署均由人工執行，**沒有 cron 或自動擷取排程**；GitHub Actions 只跑測試與 build。

## 架構與部署

```text
osu! API → ayim_pipeline.py → CSV + manifest
       → scripts/export_snapshot.py → data/snapshot.json
       → server/analytics.mjs → /api/report → web/
```

- Python：原始資料、作者與新人分類；詳見 [PIPELINE.md](PIPELINE.md)。
- 後端：Cloudflare Worker 相容的 ES module，執行篩選與聚合；唯讀，無管理端點，API 憑證不進網站。
- 前端：原生 HTML／CSS／JavaScript，無 CDN 腳本依賴；封面與頭像由 osu! 圖片服務提供。
- `npm run build`：快照、靜態檔與後端合併為 `dist/server/index.js`，可透過 Sites 部署。
- 自行託管：在自己的 Cloudflare 帳號登入後，用 `npx wrangler deploy` 部署 `wrangler.jsonc` 指定的 Worker（需另安裝 Wrangler）。無資料庫或執行時金鑰。部署後檢查 `/api/health`。

### API

`GET /api/report?mode=osu!&status=Rank&country=TW&new=true&q=...`

模式：`osu!`、`osu!taiko`、`osu!catch`、`osu!mania`、`all`。狀態：`Rank`、`Love`、`all`。國家省略代表全部；未知為 `Unknown`。回應包含 metadata、總覽、分布及完整排行榜。`GET /api/health` 提供版本與日期。

## 統計口徑

- 圖集按 ID 去重；跨模式收藏不重複加總，遊玩與難度只計選中模式。
- Mapper／Country 依圖集主創；GD 只計主要作者不同於主創的難度，按 GD 難度數排名；Host 僅計主創親自製作的難度，按其遊玩次數排名。
- 國家、新主創、搜尋均先篩選圖集，再統計該範圍的 GD／Host；搜尋曲名、藝人、主創姓名。
- 新主創：首次擁有 Ranked／Approved 圖集的年份為 2026，跨所有模式；Loved／GD 不算 Ranked 出道。未知不算新人。
- 曲風／語言按圖集數；歌曲按「曲名＋藝人」分組，避免不同藝人的同名曲混在一起。依 API 字串分組，不推測別名。
- 收藏／遊玩是擷取時累計量，不是 2026 年內新增量。API 不提供跨請求的交易快照。
- 公開快照僅包含需要的公開欄位與來源檔雜湊，不含憑證、機器路徑或快取。

## 驗證

```sh
python -m unittest -v test_ayim_pipeline.py
npm test
npm run build
```

測試涵蓋資料清理、分頁、日期、限流、新人判定、跨模式去重、收藏／遊玩對帳、GD 口徑、篩選、空結果、同名歌曲及唯讀路由。

2020 年 CSV、示意圖與 notebook 保留為歷史參考，不再作為現行入口。現行入口為 `ayim_2026.ipynb`／`ayim_pipeline.py`。[原始論壇](https://osu.ppy.sh/community/forums/topics/1213530) · [YamYA](https://osu.ppy.sh/users/4470854)



# 特戰英豪死亡自動摸魚

Windows 桌面工具：確認自己在《VALORANT》國際服對局中死亡後，切換到 Google Chrome 的Threads頁面；下一回合購買階段開始時，暫停影片並切回遊戲。再次死亡時會嘗試續播上次的影片。

程式透過螢幕畫面判斷死亡狀態，讀取本機 `ShooterGame.log` 判斷回合階段。不讀取遊戲記憶體，不向遊戲程式注入程式碼。

## 下載與啟動

1. 從 [Releases](https://github.com/MuffinHeadOo/valorant-death-switcher/releases/latest) 選擇下載：
   - **單檔案版** `ValorantDeathSwitcher-v0.1.0-standalone.exe`：直接執行，首次啟動會先解壓依賴，可能較慢。
   - **資料夾版** `ValorantDeathSwitcher-v0.1.0-win-x64.zip`：解壓後執行 `ValorantDeathSwitcher/ValorantDeathSwitcher.exe`。不要只取出其中的 EXE；它需要旁邊的 `_internal` 資料夾。
2. 需要 Windows x64 和 Google Chrome。啟動所選版本。
3. 檢查“Threads 網址”和“日誌路徑”。日誌路徑留空時，程式自動尋找國際服 `ShooterGame.log`；找不到時可點選“選擇檔案”。
4. 勾選“自動切換視窗”，點選“開始執行”。停止時點選“停止執行”。未勾選“自動切換視窗”時只記錄辨識事件，適合先檢查目前遊戲設定下的辨識效果。

首次使用 Chrome 專用視窗可能需要登入Threads。程式執行時請勿同時開啟多個執行個體。

## 工作方式與適用範圍

| 場景 | 行為 |
| --- | --- |
| 標準回合戰鬥階段，遊戲在前景，畫面連續確認本人死亡 | 開啟或切到同一個 Chrome 視窗，並嘗試播放影片 |
| 下一回合購買階段開始 | 暫停影片，嘗試切回遊戲 |
| 黑屏、畫面捕獲失敗、計分板遮擋或死亡證據不足 | 不觸發死亡切換視窗，介面顯示目前狀態 |
| 死鬥、亂鬥、訓練場或無法確認回合模式 | 不執行自動切換視窗 |

目前使用已驗證的國際服標準回合日誌辨識爆破、極速模式和火線交鋒 2v2的購買階段。程式會自動尋找遊戲視窗和畫面區域，但不同解析度、獨佔全螢幕、無邊框全螢幕、視窗化以及遊戲更新後的實際效果仍會受顯示卡驅動程式和 HUD 版面配置影響。Windows 可能拒絕背景程式切回遊戲；這時介面會記錄故障。

## 常見問題

**死亡後沒有切到瀏覽器**

- 確認已勾選“自動切換視窗”，介面顯示標準回合、戰鬥階段，並且遊戲在前景。
- 檢視“捕獲”“辨識”“判斷原因”和事件記錄。無法捕獲有效畫面時程式不會猜測死亡。
- 第一次開啟 Chrome 可能比之後慢；購買階段啟動程式有助於預熱瀏覽器。

**購買階段沒有切回遊戲**

- 檢視事件記錄是否出現“購買階段開始”。如果沒有，檢查日誌路徑和目前遊戲模式。
- 若事件記錄顯示 Windows 拒絕切回遊戲，可手動切回。程式不會向遊戲注入或模擬遊戲操作。

**Threads頁面或影片沒有恢復**

- Chrome 使用獨立的資料目錄，首次需要重新登入。關閉專用視窗後，下一次死亡會嘗試重新開啟。
- 網頁播放器可能在切換內容或重新載入後更換影片元素；此時自動續播不能保證成功。

**程式啟動失敗**

- 保持釋出包目錄完整，檢查 `%LOCALAPPDATA%\ValorantDeathSwitcher\crash.log`。
- 可透過 [問題回報模板](https://github.com/MuffinHeadOo/valorant-death-switcher/issues/new/choose) 報告版本、Windows 版本、遊戲模式、解析度、顯示模式，以及介面狀態和相關錯誤。提交日誌前請自行檢查並刪除不想公開的路徑或帳號資訊。

## 本地資料與隱私

- 配置：`%LOCALAPPDATA%\ValorantDeathSwitcher\settings.json`
- 事件記錄：同目錄 `events.log`
- 啟動異常：同目錄 `crash.log`
- Chrome 專用資料：同目錄 `chrome-profile/`

程式預設不儲存整屏截圖，也不上傳辨識畫面、遊戲日誌或設定。網頁內容由 Chrome 直接訪問你填寫的網址。上述本地資料不會包含在原始碼倉庫或釋出包中。

## 從原始碼執行與構建

需要 Windows、Python 3.12 x64 和 Google Chrome。在專案目錄執行：

```powershell
py -3.12 -m venv .venv-official
& .\.venv-official\Scripts\python.exe -m pip install -e . pytest PyInstaller
& .\run.ps1
```

執行測試和打包：

```powershell
& .\.venv-official\Scripts\python.exe -m pytest -q
& .\build.ps1
& .\build-onefile.ps1
```

資料夾版輸出位於 `dist/ValorantDeathSwitcher/`，單檔案版輸出位於 `dist-onefile/`。其中 `local-data/` 為本機測試樣本與開發環境，不進入 Git 倉庫或釋出包；缺少本機原始截圖時，對應回放測試會跳過。釋出時可將兩個版本都放入 GitHub Release。

本專案為非官方工具，與 Riot Games、Threads及 Microsoft 無關聯。

本倉庫目前未新增開源許可證；如需複用或再發布原始碼，請先聯絡倉庫所有者。

聯絡郵箱：[1608175635@qq.com](mailto:1608175635@qq.com)。

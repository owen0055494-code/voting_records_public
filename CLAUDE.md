> 繼承組織層（~/.claude/CLAUDE.md）與作品集層（程式開發作品集/CLAUDE.md）。本文件僅定義本專案特有的規範。

# voting_records_public — 集保股東會電子投票助手（公開版）

## 用途

集保（TDCC）股東會電子投票自動化工具：Selenium 開 Chrome 登入集保 e 投票網站，對未投票議案執行「全部棄權」，並截圖留存投票紀錄。這是**公開版**（私人版是 `voting_records`），規則如下：

- 不得出現身分證字號、帳號、憑證、截圖、真實座標等個資或私人設定。身分證字號只在 GUI 執行時手動輸入，不落檔。
- `config.json`、`voting_records/`、`截圖儲存區/`、`learned_*.png`、`calibration_map.png` 已在 `.gitignore`，不得 commit。提供格式參考的是 `config.example.json`（座標全為 0）。
- 公開版修改完要與私人版分開處理，不得把私人版的設定或截圖帶進來。

## 主要入口

| 入口 | 說明 |
|---|---|
| `vote_gui.py` | tkinter GUI 主程式（`__main__` 直接 `mainloop`，無命令列參數） |
| `快速啟動.bat` | 切到本資料夾後執行 `python vote_gui.py` |
| `tdcc_vote_bot.py` | 核心邏輯（`TdccBot`：登入、投票、截圖、分頁掃描），被 `vote_gui.py` 匯入；無獨立 CLI |
| `vote_gui.spec` | PyInstaller 打包設定（打包不屬於交付檢查） |

注意：`import tdcc_vote_bot` 在模組載入時會建立 `voting_records/` 資料夾（已 gitignore），乾跑時避免匯入。

## 乾跑

本專案**沒有 `--dry-run` 參數、沒有 mock、沒有測試**。所有真實流程（`open_browser`、`start_scanning`）都會開 Chrome 連到 `stockservices.tdcc.com.tw`、登入並送出投票，因此：

- **絕不執行** `python vote_gui.py`、`快速啟動.bat`，也不得手動呼叫 `TdccBot.open_browser` / `start_scanning` / `dynamic_voting_process`。
- 不登入集保與投票網站，不使用真實身分證字號、券商憑證或帳號，不寫入截圖等個資輸出。
- 要驅動真實入口做端對端乾跑，需新增 dry-run 模式或 mock（例如注入假 driver）：**需新增，待使用者決定**，不自行發明參數。

直譯器：Python 3.12 直譯器（下稱 `$PY`，路徑依各人環境，不寫進版控）。以下在專案根目錄執行，`-I -B` 避免載入外部模組與產生 `__pycache__`。

### (1)(2)(4) 入口、乾跑指令與實測狀態

| 入口 | 乾跑指令 | 狀態 |
|---|---|---|
| `tdcc_vote_bot.py` | `"$PY" -I -B -c "compile(open('tdcc_vote_bot.py',encoding='utf-8').read(),'tdcc_vote_bot.py','exec');print('OK')"`（只編譯語法，不執行、不匯入） | 已實測：輸出 `OK tdcc_vote_bot.py`，rc=0 |
| `vote_gui.py` | 同上，檔名換成 `vote_gui.py` | 已實測：輸出 `OK vote_gui.py`，rc=0 |
| `config.example.json` | `"$PY" -I -B -c "import json;print(json.load(open('config.example.json')))"` | 已實測：輸出 7 個鍵（`1`、`2`、`3`、`3_option`、`4`、`4_confirm`、`5`），值皆為 `[0, 0]` |
| `快速啟動.bat` | 無（唯一動作是啟動 GUI，GUI 可連外登入） | 未實測：執行即啟動 GUI，無法保證無副作用 |
| `vote_gui.py` 的 `--help` | 無此參數 | 未實測：沒有命令列介面，執行會直接開 GUI |
| `vote_gui.spec` | 無 | 未實測：打包不在交付範圍，且需 pyinstaller |

為何不用 `python -m py_compile`：它會在專案內寫 `__pycache__`；用 `cfile=os.devnull` 在 Windows 會報 `FileExistsError`，所以改用內建 `compile()`。

### (3) 副作用防護

- 只允許：語法編譯、讀 JSON、文件檢查。不得 `import tdcc_vote_bot` 或 `vote_gui`（前者建資料夾，後者會 import pyautogui／pynput 並可能啟動 GUI 相關元件）。
- 不得執行任何會開瀏覽器連外、登入、送出投票的指令；不 `pip install`。
- 缺 selenium、pyautogui、pynput 等套件時，一律標「未實測：缺環境」，不安裝。

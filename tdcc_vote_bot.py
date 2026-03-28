import time
import os
import re
import random
import traceback
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# 嘗試匯入 Pillow
try:
    from PIL import Image, ImageDraw, ImageFont 
    HAS_PILLOW = True
except Exception:
    HAS_PILLOW = False
    print("警告: 未安裝 Pillow 套件。")

# 嘗試匯入 PyAutoGUI
try:
    import pyautogui
    HAS_PYAUTOGUI = True
except Exception:
    HAS_PYAUTOGUI = False
    print("警告: 未安裝 PyAutoGUI。")

# 嘗試匯入 OpenCV (加速視覺辨識)
# [修正] 改用 Exception 捕捉所有錯誤，防止因為 numpy 版本衝突導致程式崩潰
try:
    import cv2
    HAS_OPENCV = True
except Exception:
    HAS_OPENCV = False
    # 不印出警告以免干擾

# 嘗試匯入 Pyperclip
try:
    import pyperclip
    HAS_CLIPBOARD = True
except Exception:
    HAS_CLIPBOARD = False
    print("警告: 未安裝 pyperclip。")

# 設定目錄
SCREENSHOT_DIR = "voting_records"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def clean_filename(text):
    return "".join([c for c in text if c.isalpha() or c.isdigit() or c in (' ', '_', '-')]).strip()

def check_file_exists(folder, stock_code, company_name):
    safe_name = clean_filename(company_name)
    try:
        files = os.listdir(folder)
    except FileNotFoundError:
        return False

    for f in files:
        if stock_code != "Unknown" and stock_code in f and len(stock_code) >= 4:
            return True
        if company_name != "Unknown" and safe_name in f and len(safe_name) > 2:
            return True
    return False

class TdccBot:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.visual_confidence = 0.8

    def human_delay(self, low=0.5, high=1.5):
        """模擬真人操作的隨機延遲"""
        time.sleep(random.uniform(low, high))

    def auto_learn_image(self, step_name, x, y):
        """堆疊式學習"""
        if not HAS_PYAUTOGUI: return
        try:
            region = (int(x - 30), int(y - 20), 60, 40)
            timestamp = int(time.time())
            new_filename = f"learned_{step_name}_{timestamp}.png"
            new_path = os.path.join(SCREENSHOT_DIR, new_filename)
            pyautogui.screenshot(new_path, region=region)
            print(f"[學習] 已紀錄特徵: {new_filename}")
        except: pass

    def locate_and_click(self, image_name_base, offset_x=0, offset_y=0, retries=2, timeout=None):
        """視覺辨識核心 — 超時制 + 漸進降低 confidence + 多尺度匹配"""
        if not HAS_PYAUTOGUI: return False

        # timeout 優先；未指定時用 retries 估算（每輪約 1 秒）
        if timeout is None:
            timeout = max(retries * 1.5, 3)

        target_files = []
        if os.path.exists(os.path.join(SCREENSHOT_DIR, image_name_base)):
            target_files.append(os.path.join(SCREENSHOT_DIR, image_name_base))
        elif os.path.exists(image_name_base):
            target_files.append(image_name_base)

        base_no_ext = os.path.splitext(image_name_base)[0]
        for f in os.listdir(SCREENSHOT_DIR):
            if f.startswith(f"learned_{base_no_ext}") and f.endswith(".png"):
                target_files.append(os.path.join(SCREENSHOT_DIR, f))

        if not target_files: return False

        # 由高到低嘗試多個 confidence 等級
        confidence_levels = [0.85, 0.75, 0.65] if HAS_OPENCV else [None]
        # 多尺度：原始 + 縮放版本
        scales = [1.0, 0.9, 1.1] if HAS_OPENCV else [1.0]

        print(f"[視覺] 搜尋中 ({len(target_files)} 樣本, 最多等 {timeout:.0f}s)...", end="", flush=True)

        start_time = time.time()
        attempt = 0
        while (time.time() - start_time) < timeout:
            attempt += 1
            # 隨著時間推移逐步放寬 confidence
            elapsed_ratio = (time.time() - start_time) / timeout
            if elapsed_ratio < 0.4:
                confs = confidence_levels[:1]   # 前 40% 時間用高 confidence
            elif elapsed_ratio < 0.7:
                confs = confidence_levels[:2]   # 中段加入中等 confidence
            else:
                confs = confidence_levels       # 後段全部嘗試

            for img_path in target_files:
                for conf in confs:
                    for scale in scales:
                        try:
                            search_img = img_path
                            # 多尺度：縮放模板後用暫存檔搜尋
                            if scale != 1.0 and HAS_OPENCV:
                                import numpy as np
                                tmpl = cv2.imread(img_path)
                                if tmpl is None:
                                    continue
                                h, w = tmpl.shape[:2]
                                new_w, new_h = int(w * scale), int(h * scale)
                                if new_w < 5 or new_h < 5:
                                    continue
                                resized = cv2.resize(tmpl, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                                tmp_path = os.path.join(SCREENSHOT_DIR, "_tmp_scaled.png")
                                cv2.imwrite(tmp_path, resized)
                                search_img = tmp_path

                            location = None
                            if conf is not None:
                                location = pyautogui.locateCenterOnScreen(
                                    search_img, confidence=conf, grayscale=True)
                            else:
                                location = pyautogui.locateCenterOnScreen(
                                    search_img, grayscale=True)

                            if location:
                                tx, ty = location
                                fx, fy = tx + offset_x, ty + offset_y
                                conf_str = f", conf={conf}" if conf else ""
                                scale_str = f", scale={scale}" if scale != 1.0 else ""
                                print(f" 鎖定! 點擊 ({fx}, {fy}{conf_str}{scale_str})")
                                pyautogui.click(fx, fy)
                                return True
                        except Exception:
                            pass

            print(".", end="", flush=True)
            # 漸進等待：前幾輪快速重試，之後間隔拉長
            wait = 0.3 if attempt <= 3 else 0.8
            time.sleep(wait)

        elapsed = time.time() - start_time
        print(f" 失敗 ({elapsed:.1f}s)。")
        return False

    def open_browser(self, user_id, coords=None):
        try:
            if self.driver:
                print("瀏覽器已經開啟中...")
                return True

            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")
            # 隱藏自動化特徵
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            prefs = {"profile.default_content_setting_values.notifications": 2,
                     "credentials_enable_service": False,
                     "profile.password_manager_enabled": False}
            options.add_experimental_option("prefs", prefs)

            self.driver = webdriver.Chrome(options=options)
            # 移除 navigator.webdriver 標記
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    // 補齊正常瀏覽器的 plugins/languages 指紋
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-TW', 'zh', 'en-US', 'en']
                    });
                    // 隱藏 Chrome DevTools Protocol 痕跡
                    window.chrome = { runtime: {} };
                """
            })
            self.wait = WebDriverWait(self.driver, 10)
            
            print("Step 0: 開啟首頁...")
            self.driver.get("https://stockservices.tdcc.com.tw/")
            self.human_delay(2.0, 3.5)

            # --- Step 1: 登入按鈕 ---
            print("Step 1: 點擊登入...")
            s1_done = False
            try:
                self.driver.find_element(By.XPATH, "//a[contains(text(), '登入')]").click()
                s1_done = True; print("-> [網頁元素] 成功。")
            except: pass

            if not s1_done:
                if self.locate_and_click("step1.png"): s1_done = True

            if not s1_done and coords and coords.get("1"):
                print("-> [座標] 點擊...")
                pyautogui.click(coords["1"])
                self.auto_learn_image("step1.png", coords["1"][0], coords["1"][1])
                s1_done = True

            self.human_delay(1.5, 3.0)

            # --- Step 2: 輸入身分證 ---
            print("Step 2: 輸入身分證...")
            s2_done = False
            try:
                inp = self.driver.find_element(By.XPATH, "//input[contains(@placeholder,'身分證')]")
                inp.click(); inp.clear(); inp.send_keys(user_id)
                s2_done = True; print("-> [網頁元素] 成功。")
            except: pass

            if not s2_done:
                if self.locate_and_click("step2.png", offset_x=150): s2_done = True

            if not s2_done and coords and coords.get("2"):
                print("-> [座標] 點擊...")
                pyautogui.click(coords["2"])
                self.auto_learn_image("step2.png", coords["2"][0], coords["2"][1])
                s2_done = True

            if s2_done:
                self.human_delay(0.3, 0.8)
                if HAS_PYAUTOGUI:
                    pyautogui.hotkey('ctrl', 'a'); pyautogui.press('backspace')
                    if HAS_CLIPBOARD:
                        pyperclip.copy(user_id); pyautogui.hotkey('ctrl', 'v')
                    else: pyautogui.typewrite(user_id)
                self.human_delay(0.5, 1.2)

            # --- Step 3: 選擇憑證 ---
            print("Step 3: 選擇憑證...")
            s3_done = False
            try:
                self.driver.find_element(By.XPATH, "//*[contains(text(),'請選擇')]").click(); self.human_delay(0.3, 0.8)
                self.driver.find_element(By.XPATH, "//*[contains(text(),'券商網路')]").click()
                s3_done = True; print("-> [網頁元素] 成功。")
            except: pass

            if not s3_done:
                if self.locate_and_click("step3.png", offset_x=150):
                    self.human_delay(0.3, 0.8)
                    if not self.locate_and_click("step3_opt.png"):
                        pyautogui.press('down'); pyautogui.press('enter')
                    s3_done = True

            if not s3_done and coords and coords.get("3"):
                print("-> [座標] 點擊...")
                pyautogui.click(coords["3"]); self.human_delay(0.3, 0.8)
                if coords.get("3_option"): pyautogui.click(coords["3_option"])
                else: pyautogui.press('down'); pyautogui.press('enter')
                self.auto_learn_image("step3.png", coords["3"][0], coords["3"][1])
                s3_done = True

            # --- Step 4: 登入按鈕 ---
            print("Step 4: 提交登入...")
            s4_done = False
            try:
                self.driver.find_element(By.XPATH, "//button[contains(text(),'登入') and not(@class='header')]").click()
                s4_done = True; print("-> [網頁元素] 成功。")
            except: pass

            if not s4_done:
                if self.locate_and_click("step4.png"): s4_done = True

            if not s4_done and coords and coords.get("4"):
                print("-> [座標] 點擊...")
                pyautogui.click(coords["4"])
                self.auto_learn_image("step4.png", coords["4"][0], coords["4"][1])
                s4_done = True
            
            self.human_delay(2.0, 3.5)

            # 重複登入確認
            try: 
                self.driver.find_element(By.XPATH, "//button[contains(text(),'確認')]").click()
                print("-> [網頁元素] 確認框。")
            except:
                if coords and coords.get("4_confirm"):
                    pyautogui.click(coords["4_confirm"]); pyautogui.press('enter')

            # --- Step 5: 權限提示 ---
            print("Step 5: 權限允許...")
            if self.locate_and_click("step5.png", timeout=15):
                print("-> [視覺] 成功。")
            elif coords and coords.get("5"):
                print("-> [座標] 點擊...")
                pyautogui.click(coords["5"])
                self.auto_learn_image("step5.png", coords["5"][0], coords["5"][1])
            else:
                print("-> 無法自動點擊權限，請手動。")

            print("登入流程結束。")
            return True

        except Exception as e:
            print(f"登入流程錯誤: {e}")
            traceback.print_exc()
            return False

    def generate_visual_map(self, coords, save_path="calibration_map.png"):
        if not HAS_PILLOW or not HAS_PYAUTOGUI: return
        try:
            screenshot = pyautogui.screenshot()
            draw = ImageDraw.Draw(screenshot)
            try: font = ImageFont.truetype("arial.ttf", 40)
            except: font = ImageFont.load_default()
            for step, pos in coords.items():
                if pos:
                    x, y = pos
                    r = 15
                    draw.ellipse((x-r, y-r, x+r, y+r), outline="red", width=5)
                    draw.text((x+r+5, y-20), str(step), fill="red", font=font, stroke_width=2, stroke_fill="white")
            screenshot.save(save_path)
            return save_path
        except: pass

    def close_browser(self):
        if self.driver:
            print("正在關閉瀏覽器...")
            try: self.driver.quit()
            except: pass
            self.driver = None
            self.wait = None

    def smart_save_screenshot(self, filepath):
        if not self.driver: return False
        if not HAS_PILLOW:
            self.driver.save_screenshot(filepath); return True

        try:
            current_scroll_y = self.driver.execute_script("return window.scrollY;")
            if current_scroll_y > 0:
                self.driver.execute_script("window.scrollTo(0, 0);"); time.sleep(0.5)
            
            self.driver.save_screenshot(filepath)
            
            try:
                top_ele = self.driver.find_element(By.XPATH, "//*[contains(text(), '下列為') or contains(text(), '貴股東對')]")
            except:
                print("裁切警告：找不到頂部標題，保留原圖。"); return True

            try:
                bot_ele = self.driver.find_element(By.XPATH, "//*[contains(text(), '最近一次投票時間')]")
            except:
                try: bot_ele = self.driver.find_element(By.XPATH, "//*[contains(text(), '證券代號')]/ancestor::div[1]")
                except: print("裁切警告：找不到底部定位點，保留原圖。"); return True

            img = Image.open(filepath)
            window_width = self.driver.execute_script("return window.innerWidth")
            scale = img.width / window_width if window_width > 0 else 1
            
            top_y = top_ele.location['y']
            if "最近一次投票時間" in bot_ele.text:
                bot_y = bot_ele.location['y'] + bot_ele.size['height']
            else:
                bot_y = bot_ele.location['y'] + bot_ele.size['height'] + 50

            crop_top = top_y * scale
            crop_bottom = bot_y * scale
            
            final_top = max(0, crop_top - 10)
            final_bottom = min(img.height, crop_bottom + 10)
            
            if final_bottom <= final_top: return True
                
            img_cropped = img.crop((0, final_top, img.width, final_bottom))
            img_cropped.save(filepath)
            print(f"精準裁切成功: {os.path.basename(filepath)}")
            return True

        except Exception as e:
            print(f"裁切過程發生錯誤 (保留原圖): {e}"); return True

    def dynamic_voting_process(self, stop_event):
        print(">>> 進入動態投票模式 (偵測畫面中)...")
        max_loops = 30; loop_count = 0
        while loop_count < max_loops:
            loop_count += 1; self.human_delay(0.8, 1.5)
            if stop_event.is_set(): return False
            try:
                confirm_btns = self.driver.find_elements(By.XPATH, "//button[contains(text(), '確認')]")
                real_confirm = None
                for btn in confirm_btns:
                    if "確認投票結果" not in btn.text and btn.is_displayed():
                        real_confirm = btn; break
                if real_confirm:
                    print(f"[動作] 點擊確認: {real_confirm.text}")
                    self.driver.execute_script("arguments[0].click();", real_confirm); return True

                final_submit = self.driver.find_elements(By.XPATH, "//button[contains(text(), '確認投票結果')]")
                if final_submit and final_submit[0].is_displayed():
                    print("[動作] 提交投票...")
                    self.driver.execute_script("arguments[0].click();", final_submit[0]); continue

                modal_next = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'modal')]//button[contains(text(), '下一步')]")
                if modal_next and modal_next[0].is_displayed():
                    print("[動作] 點擊提示框下一步...")
                    self.driver.execute_script("arguments[0].click();", modal_next[0]); self.human_delay(0.3, 0.8); continue

                abstain = self.driver.find_elements(By.XPATH, "//a[contains(., '全部棄權')]")
                nxt = self.driver.find_elements(By.XPATH, "//button[contains(text(), '下一步') or @value='下一步']")
                if abstain and nxt and abstain[0].is_displayed():
                    print("[動作] 執行棄權並下一步...")
                    self.driver.execute_script("arguments[0].click();", abstain[0]); self.human_delay(0.3, 0.8)
                    self.driver.execute_script("arguments[0].click();", nxt[0]); continue
                    
                if nxt and nxt[0].is_displayed():
                    print("[動作] 點擊下一步...")
                    self.driver.execute_script("arguments[0].click();", nxt[0]); continue
            except Exception: pass
        return False

    # ── 分頁工具 ──────────────────────────────────────────

    LIST_URL = "https://stockservices.tdcc.com.tw/evote/shareholder/000/tc_estock_welshas_tmp.html?top=1#"

    def _get_total_pages(self):
        """偵測分頁：回傳總頁數（無分頁元件時回傳 1）。"""
        try:
            # 常見型態 1: 頁碼連結 (1 2 3 ... 8)
            page_links = self.driver.find_elements(
                By.XPATH, "//a[contains(@href,'page') or contains(@onclick,'page') or contains(@ng-click,'page')]")
            nums = []
            for a in page_links:
                m = re.search(r"(\d+)", a.text.strip())
                if m: nums.append(int(m.group(1)))
            if nums: return max(nums)

            # 常見型態 2: pagination 容器裡的數字連結
            pagi_links = self.driver.find_elements(
                By.XPATH, "//*[contains(@class,'paginat') or contains(@class,'pager')]//a")
            for a in pagi_links:
                m = re.search(r"(\d+)", a.text.strip())
                if m: nums.append(int(m.group(1)))
            if nums: return max(nums)

            # 常見型態 3: 「共 X 頁」文字
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            m = re.search(r"共\s*(\d+)\s*頁", body_text)
            if m: return int(m.group(1))

            # 常見型態 4: 「下一頁」按鈕存在代表至少 2 頁
            nxt = self.driver.find_elements(
                By.XPATH, "//*[contains(text(),'下一頁') or contains(text(),'›') or contains(@aria-label,'Next')]")
            if nxt: return -1  # 未知總頁數，用逐頁探索模式

        except Exception:
            pass
        return 1

    def _goto_page(self, page_num):
        """切換到指定頁碼，回傳是否成功。"""
        try:
            # 嘗試點擊頁碼連結
            page_links = self.driver.find_elements(
                By.XPATH, f"//a[normalize-space(text())='{page_num}']")
            for link in page_links:
                try:
                    parent_classes = self.driver.execute_script(
                        "return arguments[0].parentElement.className || ''", link)
                    # 確認是分頁區域的連結而非其他偶然的數字連結
                    if link.is_displayed():
                        self.driver.execute_script("arguments[0].click();", link)
                        self.human_delay(1.5, 2.5)
                        self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr")))
                        return True
                except Exception:
                    continue

            # 備案：如果有 onclick 含頁碼的元素
            js_links = self.driver.find_elements(
                By.XPATH, f"//*[contains(@onclick,'{page_num}') and (contains(@onclick,'page') or contains(@onclick,'Page'))]")
            for link in js_links:
                if link.is_displayed():
                    self.driver.execute_script("arguments[0].click();", link)
                    self.human_delay(1.5, 2.5)
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr")))
                    return True

        except Exception as e:
            print(f"[分頁] 切換到第 {page_num} 頁失敗: {e}")
        return False

    def _goto_next_page(self):
        """點擊「下一頁」，回傳是否成功。"""
        try:
            nxt_btns = self.driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'下一頁') or contains(text(),'›') or contains(text(),'Next') or contains(@aria-label,'Next')]")
            for btn in nxt_btns:
                if btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", btn)
                    self.human_delay(1.5, 2.5)
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr")))
                    return True
        except Exception:
            pass
        return False

    def _back_to_list(self, page_num=None):
        """返回列表並切回指定頁碼。"""
        self.driver.get(self.LIST_URL)
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr")))
        self.human_delay(1.5, 2.5)
        if page_num and page_num > 1:
            self._goto_page(page_num)

    # ── 單頁截圖掃描 ──────────────────────────────────────

    def _scan_page_for_screenshots(self, save_dir, stop_event, current_page):
        """掃描當前頁面上所有缺截圖的股票，逐一補截圖。回傳本頁補了幾張。"""
        captured = 0
        while not stop_event.is_set():
            self.human_delay(0.8, 1.2)
            try:
                rows = self.driver.find_elements(By.XPATH, "//tr")
            except WebDriverException:
                self._back_to_list(current_page)
                continue

            target_row = None; fallback_code = "Unknown"
            for row in rows:
                try:
                    row_text = row.text
                    if not ("修改" in row_text and "查詢" in row_text and "撤銷" in row_text):
                        continue
                    temp_code = "Unknown"
                    match_code = re.search(r"\b(\d{4})\b", row_text)
                    if match_code: temp_code = match_code.group(1)
                    if temp_code != "Unknown" and check_file_exists(save_dir, temp_code, "Unknown"):
                        continue
                    print(f"  發現缺截圖目標: {temp_code if temp_code != 'Unknown' else '待辨識'}")
                    target_row = row; fallback_code = temp_code; break
                except Exception:
                    continue

            if not target_row:
                break  # 本頁全部齊全

            try:
                query_btn = target_row.find_element(By.XPATH, ".//a[contains(text(), '查詢')]")
                self.driver.execute_script("arguments[0].click();", query_btn)
                self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), '表決權總數') or contains(text(), '選舉權')]")))
                self.human_delay(1.2, 2.0)

                timestamp = int(time.time())
                temp_filename = f"temp_{timestamp}.png"
                temp_filepath = os.path.join(save_dir, temp_filename)
                self.smart_save_screenshot(temp_filepath)

                final_code = "Unknown"; final_name = "Unknown"
                try:
                    header_ele = self.driver.find_element(By.XPATH, "//*[contains(text(), '貴股東對')]")
                    header_text = header_ele.text.strip()
                    match = re.search(r"貴股東對\s*(\d{4})\s+(.+)", header_text)
                    if match:
                        final_code = match.group(1)
                        final_name = match.group(2).split('114')[0].strip()
                    else:
                        m_code = re.search(r"(\d{4})", header_text)
                        final_code = m_code.group(1) if m_code else final_code
                except Exception:
                    print("  詳細頁標題辨識失敗，將使用列表代號。")

                if final_code == "Unknown" and fallback_code != "Unknown":
                    final_code = fallback_code
                    print(f"  啟用備案代號: {final_code}")

                if final_code != "Unknown" or final_name != "Unknown":
                    safe_name = clean_filename(final_name)
                    if final_code == "Unknown": new_filename = f"{safe_name}.png"
                    elif final_name == "Unknown": new_filename = f"{final_code}.png"
                    else: new_filename = f"{safe_name}_{final_code}.png"
                    new_filepath = os.path.join(save_dir, new_filename)
                    try:
                        if os.path.exists(temp_filepath):
                            if os.path.exists(new_filepath): os.remove(new_filepath)
                            os.rename(temp_filepath, new_filepath)
                            print(f"  更名成功: {new_filename}")
                    except OSError:
                        pass
                else:
                    print("  警告：無法辨識資訊，保留暫存檔。")

                captured += 1
                print(f"  返回列表 (第 {current_page} 頁)...")
                self._back_to_list(current_page)

            except Exception as e:
                print(f"  截圖異常: {e}")
                try:
                    self._back_to_list(current_page)
                except Exception:
                    break

        return captured

    # ── 主流程 ────────────────────────────────────────────

    def start_scanning(self, save_dir, stop_event):
        if not self.driver: print("錯誤：瀏覽器未開啟。"); return
        if not os.path.exists(save_dir):
            try: os.makedirs(save_dir)
            except OSError: print(f"錯誤: 無法建立資料夾 {save_dir}"); return

        print("=== 開始自動化流程 ===")
        try:
            if not self.driver.find_elements(By.XPATH, "//tr"):
                print("警告：未偵測到股票列表，請確認是否已登入完成。")
        except Exception:
            pass

        try:
            while not stop_event.is_set():
                cycle_action_taken = False

                # ── 階段一：投票（僅處理當前頁面的未投票項目） ──
                print("\n=== [檢查] 是否有未投票股票 ===")
                try:
                    vote_btns = self.driver.find_elements(
                        By.XPATH, "//tr[.//td[contains(text(), '未投票')]]//a[contains(text(), '投票')]")
                    if vote_btns:
                        print("發現未投票項目，開始投票流程...")
                        self.driver.execute_script("arguments[0].click();", vote_btns[0])
                        self.dynamic_voting_process(stop_event)
                        print("投票完成，返回列表...")
                        self.human_delay(2.5, 4.0)
                        cycle_action_taken = True
                    else:
                        print("目前無須投票。")
                except Exception as e:
                    print(f"投票階段異常: {e}")
                    try:
                        self.driver.get(self.LIST_URL); self.human_delay(2.5, 4.0)
                    except Exception:
                        pass

                if stop_event.is_set(): break

                # ── 階段二：跨頁補截圖 ──
                print("\n=== [檢查] 是否有缺漏截圖 (全頁掃描) ===")

                # 先回到第 1 頁偵測總頁數
                try:
                    self.driver.get(self.LIST_URL)
                    self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr")))
                    self.human_delay(1.0, 2.0)
                except Exception:
                    pass

                total_pages = self._get_total_pages()
                if total_pages == -1:
                    # 未知總頁數 → 逐頁探索直到「下一頁」消失
                    print(f"[分頁] 偵測到分頁（頁數未知），將逐頁掃描...")
                    max_explore = 20  # 安全上限
                elif total_pages > 1:
                    print(f"[分頁] 偵測到共 {total_pages} 頁")
                    max_explore = total_pages
                else:
                    print("[分頁] 單頁模式")
                    max_explore = 1

                total_captured = 0
                for pg in range(1, max_explore + 1):
                    if stop_event.is_set(): break

                    if pg > 1:
                        # 頁數已知用 _goto_page，未知用 _goto_next_page
                        if total_pages > 0:
                            if not self._goto_page(pg):
                                print(f"[分頁] 無法切到第 {pg} 頁，掃描結束。")
                                break
                        else:
                            if not self._goto_next_page():
                                print(f"[分頁] 已無下一頁，掃描結束。")
                                break

                    print(f"\n--- 掃描第 {pg} 頁 ---")
                    captured = self._scan_page_for_screenshots(save_dir, stop_event, pg)
                    total_captured += captured

                    if captured == 0:
                        print(f"  第 {pg} 頁截圖皆已齊全。")
                    else:
                        print(f"  第 {pg} 頁補了 {captured} 張截圖。")
                        cycle_action_taken = True

                if total_captured > 0:
                    print(f"\n[結果] 本輪共補了 {total_captured} 張截圖。")
                else:
                    print("\n[結果] 所有頁面的截圖皆已齊全。")

                if total_captured > 0:
                    cycle_action_taken = True

                if not cycle_action_taken:
                    print("\n>>> 所有工作已完成！等待 5 秒後重新掃描... (按停止鈕可結束)")
                    for _ in range(5):
                        if stop_event.is_set(): break
                        time.sleep(1)
                else:
                    print("\n>>> 本輪有動作，稍後重新掃描...")
                    self.human_delay(1.5, 3.0)

        except Exception as e:
            print(f"自動化流程發生錯誤: {e}"); traceback.print_exc()
        finally:
            print("自動化流程已暫停。")
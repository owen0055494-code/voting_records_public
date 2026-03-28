import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from PIL import Image, ImageTk
import threading
import time
import sys
import os
import json
import pyautogui
from pynput import keyboard
import tdcc_vote_bot

class TemplateCaptureWindow:
    """全螢幕拖曳框選，截取指定 UI 元素作為視覺辨識模板。"""

    STEPS = [
        ("step1",     "登入按鈕 (右上角)"),
        ("step2",     "身分證輸入框"),
        ("step3",     "憑證種類下拉選單"),
        ("step3_opt", "下拉選單中的憑證選項"),
        ("step4",     "表單登入按鈕"),
        ("step5",     "授權視窗的允許按鈕"),
    ]

    def __init__(self, root, step_name, step_desc, save_path, on_done_cb):
        self.root       = root
        self.step_name  = step_name
        self.step_desc  = step_desc
        self.save_path  = save_path
        self.on_done_cb = on_done_cb

        self.start_x = self.start_y = 0
        self.rect_id    = None
        self.screenshot = None
        self.scale_x = self.scale_y = 1.0

        # 縮小主視窗後，稍等畫面穩定再截圖
        self.root.iconify()
        self.root.after(450, self._take_and_show)

    def _take_and_show(self):
        self.screenshot = pyautogui.screenshot()
        shot_w, shot_h  = self.screenshot.size

        self.win = tk.Toplevel(self.root)
        self.win.attributes('-fullscreen', True)
        self.win.attributes('-topmost', True)
        self.win.configure(cursor='crosshair')
        self.win.focus_force()
        self.win.update_idletasks()

        disp_w = self.win.winfo_screenwidth()
        disp_h = self.win.winfo_screenheight()
        self.scale_x = shot_w / disp_w
        self.scale_y = shot_h / disp_h

        display_img = self.screenshot.resize((disp_w, disp_h), Image.LANCZOS)
        self.tk_img  = ImageTk.PhotoImage(display_img)

        self.canvas = tk.Canvas(self.win, highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img)

        # 頂部說明列
        self.canvas.create_rectangle(0, 0, disp_w, 46, fill='#212121', outline='')
        self.canvas.create_text(disp_w // 2, 23,
            text=f"拖曳框選 [{self.step_desc}] 的範圍，放開滑鼠即儲存    |    ESC 取消",
            fill='#FFD600', font=('微軟正黑體', 12, 'bold'))

        self.canvas.bind('<ButtonPress-1>',   self._on_press)
        self.canvas.bind('<B1-Motion>',       self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.win.bind('<Escape>',             self._on_cancel)

    def _on_press(self, e):
        self.start_x, self.start_y = e.x, e.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

    def _on_drag(self, e):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, e.x, e.y,
            outline='#FF1744', width=2, dash=(5, 3))

    def _on_release(self, e):
        x1, y1 = min(self.start_x, e.x), min(self.start_y, e.y)
        x2, y2 = max(self.start_x, e.x), max(self.start_y, e.y)

        if (x2 - x1) < 8 or (y2 - y1) < 8:
            return  # 框選太小，忽略

        px1 = int(x1 * self.scale_x)
        py1 = int(y1 * self.scale_y)
        px2 = int(x2 * self.scale_x)
        py2 = int(y2 * self.scale_y)

        try:
            self.screenshot.crop((px1, py1, px2, py2)).save(self.save_path)
        except Exception as ex:
            messagebox.showerror("錯誤", f"儲存模板失敗：{ex}", parent=self.root)
            self._cleanup(False)
            return

        self._cleanup(True)

    def _on_cancel(self, event=None):
        self._cleanup(False)

    def _cleanup(self, saved):
        try:
            self.win.destroy()
        except Exception:
            pass
        self.root.deiconify()
        self.root.focus_force()
        if self.on_done_cb:
            self.on_done_cb(saved)


class TextRedirector(object):
    def __init__(self, widget, tag="stdout"):
        self.widget = widget; self.tag = tag
    def write(self, str):
        try:
            self.widget.configure(state="normal")
            self.widget.insert("end", str, (self.tag,)); self.widget.see("end")
            self.widget.configure(state="disabled")
        except: pass
        try:
            if sys.__stdout__: sys.__stdout__.write(str)
        except: pass
    def flush(self): pass

class VoteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("集保自動投票助手 v2.2 (堆疊學習版)")
        self.root.geometry("800x850") 
        
        self.save_dir = tk.StringVar()
        default_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "截圖儲存區")
        self.save_dir.set(os.path.normpath(default_base))
        
        self.user_id_var = tk.StringVar(value="")
        self.is_id_visible = False
        
        self.is_running = False
        self.stop_event = threading.Event()
        
        # 1:登入鈕, 2:輸入框, 3:下拉選單, 3_option:選項, 4:登入鈕, 4_confirm:確認框, 5:權限
        self.step_coords = {}
        self.load_config()
        
        self.is_calibrating = False
        self.current_calib_step_list = []
        self.keyboard_listener = None

        self.template_btns = {}
        self.bot = tdcc_vote_bot.TdccBot()
        self._create_widgets()

    def _create_widgets(self):
        # 1. 基本設定
        frame_basic = tk.LabelFrame(self.root, text="基本設定", padx=10, pady=10)
        frame_basic.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_basic, text="截圖儲存:").grid(row=0, column=0, sticky="w")
        tk.Entry(frame_basic, textvariable=self.save_dir, width=50).grid(row=0, column=1, padx=5)
        tk.Button(frame_basic, text="瀏覽...", command=self.browse_folder).grid(row=0, column=2)

        tk.Label(frame_basic, text="身分證號:").grid(row=1, column=0, sticky="w", pady=5)
        id_container = tk.Frame(frame_basic)
        id_container.grid(row=1, column=1, sticky="w", padx=5)
        self.entry_id = tk.Entry(id_container, textvariable=self.user_id_var, width=40, show="*")
        self.entry_id.pack(side="left", fill="y")
        self.btn_eye = tk.Button(id_container, text="👁️", width=3, command=self.toggle_id)
        # [修改] 增加 padx 左邊距，讓按鈕往右移
        self.btn_eye.pack(side="left", padx=(10, 0))

        # 2. 座標定位
        frame_coord = tk.LabelFrame(self.root, text="滑鼠座標定位 (F10紀錄 -> 自動產生視覺圖)", padx=10, pady=10)
        frame_coord.pack(fill="x", padx=10, pady=5)
        
        self.btn_calib = tk.Button(frame_coord, text="開始定位 (請依序移動滑鼠並按 F10)", command=self.start_calibration, bg="#FF9800", fg="white")
        self.btn_calib.pack(fill="x", pady=5)
        
        self.lbl_coords = tk.Label(frame_coord, text=self.get_coords_text(), justify="left", font=("Consolas", 9))
        self.lbl_coords.pack(anchor="w")
        
        self.btn_visual = tk.Button(frame_coord, text="檢視定位圖", command=self.show_visual_map, state="disabled")
        self.btn_visual.pack(anchor="e")

        # 3. 視覺模板管理
        frame_tmpl = tk.LabelFrame(self.root, text="視覺模板管理（可解決授權視窗無法自動點擊的問題）", padx=10, pady=8)
        frame_tmpl.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_tmpl,
            text="點擊下方步驟按鈕 → 主視窗縮小 → 在螢幕上拖曳框選對應元素 → 放開滑鼠完成。",
            font=("微軟正黑體", 9), fg="#555555").pack(anchor="w", pady=(0, 5))

        grid_frame = tk.Frame(frame_tmpl)
        grid_frame.pack(fill="x")

        for i, (sname, sdesc) in enumerate(TemplateCaptureWindow.STEPS):
            col = i % 2
            row = i // 2
            grid_frame.columnconfigure(col, weight=1)
            has = os.path.exists(
                os.path.join(tdcc_vote_bot.SCREENSHOT_DIR, f"{sname}.png"))
            btn = tk.Button(grid_frame,
                text=self._tmpl_btn_text(sname, sdesc, has),
                bg="#C8E6C9" if has else "#ECEFF1",
                anchor="w", relief="groove",
                command=lambda s=sname, d=sdesc: self.capture_template(s, d))
            btn.grid(row=row, column=col, padx=4, pady=2, sticky="ew")
            self.template_btns[sname] = (btn, sdesc)

        # 4. 操作面板
        frame_ctrl = tk.LabelFrame(self.root, text="執行操作", padx=10, pady=10)
        frame_ctrl.pack(fill="x", padx=10, pady=5)

        btn_frame = tk.Frame(frame_ctrl)
        btn_frame.pack(fill="x")
        self.btn_open = tk.Button(btn_frame, text="1. 開啟網頁 (自動登入)", command=self.open_browser_action, bg="#2196F3", fg="white", width=25, height=2)
        self.btn_open.pack(side="left", padx=10)
        self.btn_start = tk.Button(btn_frame, text="2. 開始自動執行", command=self.start_bot, bg="#4CAF50", fg="white", width=25, height=2, state="disabled")
        self.btn_start.pack(side="left", padx=10)
        self.btn_stop = tk.Button(btn_frame, text="🛑 停止運作", command=self.stop_bot, bg="#f44336", fg="white", width=15, height=2, state="disabled")
        self.btn_stop.pack(side="right", padx=10)

        # 4. 紀錄
        frame_log = tk.LabelFrame(self.root, text="執行紀錄", padx=5, pady=5)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(frame_log, state='disabled', height=10)
        self.log_text.pack(fill="both", expand=True)
        sys.stdout = TextRedirector(self.log_text)
        sys.stderr = TextRedirector(self.log_text, tag="stderr")

        if os.path.exists("calibration_map.png"):
            self.btn_visual.config(state="normal")

    def toggle_id(self):
        if self.is_id_visible:
            self.entry_id.config(show="*"); self.btn_eye.config(text="👁️")
            self.is_id_visible = False
        else:
            self.entry_id.config(show=""); self.btn_eye.config(text="🔒")
            self.is_id_visible = True

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: self.save_dir.set(path)

    # --- 視覺模板截取 ---
    def _tmpl_btn_text(self, sname, sdesc, exists):
        icon = "✓" if exists else "○"
        return f"  {icon}  截取：{sdesc}"

    def capture_template(self, step_name, step_desc):
        save_path = os.path.join(tdcc_vote_bot.SCREENSHOT_DIR, f"{step_name}.png")
        TemplateCaptureWindow(
            self.root, step_name, step_desc, save_path,
            lambda saved: self._on_template_done(step_name, step_desc, saved))

    def _on_template_done(self, step_name, step_desc, saved):
        if saved:
            print(f"[模板] {step_name}.png 儲存完成，下次執行將直接使用視覺辨識。")
            if step_name in self.template_btns:
                btn, sdesc = self.template_btns[step_name]
                btn.config(
                    text=self._tmpl_btn_text(step_name, sdesc, True),
                    bg="#C8E6C9")
        else:
            print(f"[模板] 截取已取消。")

    # --- 座標定位邏輯 ---
    def get_coords_text(self):
        s = "目前設定狀態: "
        count = len([v for v in self.step_coords.values() if v])
        s += f"已設定 {count} 個點位。"
        if count > 0: s += " (可點擊右下角檢視圖片)"
        return s

    def start_calibration(self):
        if self.is_calibrating: return
        self.is_calibrating = True
        
        self.current_calib_step_list = [
            ("1", "首頁右上角 [登入] 按鈕"),
            ("2", "身分證字號 輸入框"),
            ("3", "憑證種類 [下拉選單]"),
            ("3_option", "下拉選單中的 [券商網路下單憑證] 選項"),
            ("4", "登入表單下方的 [登入] 按鈕"),
            ("4_confirm", "重複登入提示框的 [確認] 按鈕"),
            ("5", "瀏覽器權限提示的 [允許] 按鈕")
        ]
        
        self.btn_calib.config(text="定位中... 請依序移動滑鼠並按 F10", bg="#E91E63")
        print("\n=== 進入定位模式 (共 7 個點位) ===")
        self.print_next_step_hint()
        
        self.keyboard_listener = keyboard.GlobalHotKeys({'<f10>': self.on_f10_press})
        self.keyboard_listener.start()

    def print_next_step_hint(self):
        if self.current_calib_step_list:
            key, desc = self.current_calib_step_list[0]
            print(f">>> 請移動滑鼠到 [{desc}] 位置，然後按 F10")
        else:
            print("所有步驟設定完成！正在產生視覺化圖片...")
            self.stop_calibration()

    def on_f10_press(self):
        if not self.current_calib_step_list: return
        
        x, y = pyautogui.position()
        key, desc = self.current_calib_step_list.pop(0)
        
        self.step_coords[key] = (x, y)
        print(f"已紀錄 [{desc}]: ({x}, {y})")
        
        self.print_next_step_hint()

    def stop_calibration(self):
        self.is_calibrating = False
        if self.keyboard_listener:
            self.keyboard_listener.stop(); self.keyboard_listener = None
        self.btn_calib.config(text="重新設定座標 (F10)", bg="#FF9800")
        self.save_config()
        
        img_path = self.bot.generate_visual_map(self.step_coords)
        if img_path:
            self.btn_visual.config(state="normal")
            self.show_visual_map()

    def show_visual_map(self):
        try:
            top = tk.Toplevel(self.root)
            top.title("座標定位視覺化預覽")
            img = Image.open("calibration_map.png")
            img.thumbnail((800, 600))
            tk_img = ImageTk.PhotoImage(img)
            lbl = tk.Label(top, image=tk_img)
            lbl.image = tk_img 
            lbl.pack()
        except Exception as e:
            print(f"無法顯示圖片: {e}")

    def save_config(self):
        try:
            with open("config.json", "w") as f:
                data = {str(k): v for k,v in self.step_coords.items()}
                json.dump(data, f)
        except: pass

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    data = json.load(f)
                    self.step_coords = data
            except: pass

    # --- 執行 ---
    def open_browser_action(self):
        uid = self.user_id_var.get().strip()
        if not uid: messagebox.showerror("錯誤", "請輸入身分證字號"); return
        self.btn_open.config(state="disabled")
        threading.Thread(target=self._open_thread, args=(uid, self.step_coords)).start()

    def _open_thread(self, uid, coords):
        success = self.bot.open_browser(uid, coords)
        if success:
            self.root.after(0, lambda: self.btn_start.config(state="normal", bg="#4CAF50"))
            self.root.after(0, lambda: self.btn_open.config(text="網頁已開啟", bg="#81C784"))
        else:
            self.root.after(0, lambda: self.btn_open.config(state="normal"))

    def start_bot(self):
        path = self.save_dir.get()
        self.is_running = True; self.stop_event.clear()
        self.btn_start.config(state="disabled", text="執行中...", bg="#a5d6a7")
        self.btn_stop.config(state="normal")
        self.btn_open.config(state="disabled")
        threading.Thread(target=self._run_bot, args=(path,)).start()

    def _run_bot(self, path):
        try: self.bot.start_scanning(path, self.stop_event)
        except Exception as e: print(e)
        finally: self.root.after(0, self.finish_bot)

    def stop_bot(self):
        if not self.is_running: return
        print("\n[系統] 正在停止..."); self.stop_event.set()
        self.btn_stop.config(state="disabled")

    def finish_bot(self):
        self.is_running = False
        self.btn_start.config(state="normal", text="開始自動執行", bg="#4CAF50")
        self.btn_stop.config(state="disabled")
        print("=== 流程結束 ===")

    def on_close(self):
        if self.is_running: self.stop_event.set()
        if self.bot: self.bot.close_browser()
        if self.keyboard_listener: self.keyboard_listener.stop()
        self.root.destroy(); sys.exit()

if __name__ == "__main__":
    root = tk.Tk()
    app = VoteApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
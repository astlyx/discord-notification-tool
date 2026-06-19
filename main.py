#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════╗
║            Discord Notification Tool         ║
╚══════════════════════════════════════════════╝
"""

import sys, json, asyncio, threading, requests
from datetime import datetime
from pathlib import Path

try:
    import discord
except ImportError:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    _a = QApplication(sys.argv)
    QMessageBox.critical(None, "Missing Package",
        "discord.py is not installed.\n\npip install discord.py")
    sys.exit(1)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame,
    QStackedWidget, QCheckBox, QSizePolicy
)
from PyQt6.QtCore  import QThread, pyqtSignal, Qt, QTimer, QSize
from PyQt6.QtGui   import QFont, QColor, QPalette, QPainter, QPixmap, QIcon

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

def _cfg_path() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "config.json"
    return Path(__file__).parent / "config.json"

def load_cfg() -> dict:
    p = _cfg_path()
    if p.exists():
        try:
            data = json.loads(p.read_text("utf-8"))
            # Migrate old ntfy_server + ntfy_topic format → ntfy_url
            if not data.get("ntfy_url"):
                srv = data.get("ntfy_server","").rstrip("/")
                top = data.get("ntfy_topic","").strip()
                if srv and top:
                    data["ntfy_url"] = f"{srv}/{top}"
                    save_cfg(data)
            return data
        except: pass
    return {"token":"","ntfy_url":"",
            "watched_channels":[],"keywords":[],"logs":[]}

def save_cfg(c: dict):
    try: _cfg_path().write_text(json.dumps(c, indent=2, ensure_ascii=False), "utf-8")
    except Exception as e: print(f"[cfg] {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  NTFY
# ══════════════════════════════════════════════════════════════════════════════

def ntfy_send(title: str, body: str) -> bool:
    c   = load_cfg()
    url = c.get("ntfy_url","").strip()
    if not url: return False
    try:
        r = requests.post(
            url,
            data=body.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": "4",
                "Tags":     "bell",
            },
            timeout=5
        )
        return r.ok
    except Exception as e:
        print(f"[ntfy] {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  DISCORD BOT THREAD
# ══════════════════════════════════════════════════════════════════════════════

class BotThread(QThread):
    sig_ch       = pyqtSignal(list)   # list of {id, name, guild}
    sig_hit      = pyqtSignal(dict)   # keyword detection entry
    sig_st       = pyqtSignal(str, str)  # (message, level)
    sig_activity = pyqtSignal(str)    # watched-channel activity (no keyword match)

    def __init__(self, token: str):
        super().__init__()
        self._token = token
        self._loop: asyncio.AbstractEventLoop = None
        self._cli:  discord.Client            = None
        self._dead  = False

    def run(self):
        self._dead = False
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        intents = discord.Intents.default()
        intents.message_content = True
        self._cli = discord.Client(intents=intents)
        me = self

        @self._cli.event
        async def on_ready():
            chs = [{"id":str(c.id),"name":c.name,"guild":g.name}
                   for g in me._cli.guilds for c in g.text_channels]
            me.sig_ch.emit(chs)
            me.sig_st.emit(f"🔔  {me._cli.user}  ·  connected", "ok")

        @self._cli.event
        async def on_message(msg: discord.Message):
            if msg.author == me._cli.user: return
            cfg = load_cfg()

            # ── Check watched channels ──
            if str(msg.channel.id) not in cfg.get("watched_channels",[]):
                return

            # ── Message Content Intent kontrolü ──
            if not msg.content and not msg.attachments:
                me.sig_st.emit(
                    "⚠  Message content is empty — Check Message Content Intent in Discord Dev Portal."
                    "Message Content Intent must be enabled.", "warn")
                return

            me.sig_activity.emit(f"#{msg.channel.name}  ·  @{msg.author.name}")

            low = msg.content.lower()
            matched = False
            for kw in cfg.get("keywords",[]):
                if kw.lower() in low:
                    matched = True
                    e = {
                        "ts"     : datetime.now().strftime("%H:%M:%S"),
                        "date"   : datetime.now().strftime("%d.%m.%Y"),
                        "guild"  : getattr(msg.guild,"name","?"),
                        "channel": msg.channel.name,
                        "author" : msg.author.name,
                        "keyword": kw,
                        "content": msg.content[:300],
                    }
                    me.sig_hit.emit(e)
                    c2 = load_cfg()
                    c2.setdefault("logs",[]).insert(0, dict(e, ts=datetime.now().isoformat()))
                    c2["logs"] = c2["logs"][:200]
                    save_cfg(c2)
                    ntfy_send("Notification",
                              f"#{msg.channel.name}  @{msg.author.name}\n{msg.content[:200]}")
                    break

        try:
            self._loop.run_until_complete(self._cli.start(self._token))
        except discord.LoginFailure:
            me.sig_st.emit("☠  Invalid token — Check settings", "err")
        except asyncio.CancelledError:
            pass
        except Exception as ex:
            if not me._dead:
                me.sig_st.emit(f"☠  {ex}", "err")

    def stop(self):
        self._dead = True
        if self._cli and self._loop and not self._loop.is_closed():
            fut = asyncio.run_coroutine_threadsafe(self._cli.close(), self._loop)
            try: fut.result(timeout=5)
            except: pass

# ══════════════════════════════════════════════════════════════════════════════
#  STYLESHEET
# ══════════════════════════════════════════════════════════════════════════════

QSS = """
* { font-family: 'Segoe UI', Arial; color: #c8b8e8; font-size: 13px; }
QMainWindow, QWidget { background: #0c0a12; }

/* ─── Sidebar ─── */
#sidebar { background: #08060f; border-right: 1px solid #1c1530; }
#logo_sym  { color: #8c0a28; font-size: 30px; background: transparent; padding: 0; }
#logo_txt  { color: #d4aa40; font-size: 8px; letter-spacing: 4px;
             font-weight: bold; background: transparent; }
#ver_lbl   { color: #2e2440; font-size: 10px; background: transparent; }
#nav_btn {
    background: transparent; border: none;
    border-left: 3px solid transparent;
    color: #4e3e6e; font-size: 13px;
    padding: 13px 18px; text-align: left;
}
#nav_btn:hover   { background: #120c20; color: #c8b8e8; border-left-color: #4a1880; }
#nav_btn:checked { background: #160e28; color: #d4aa40;
                   border-left-color: #8c0a28; font-weight: bold; }

/* ─── Separators ─── */
#sep     { background: #1c1530; max-height: 1px; }
#sep_dot { color: #2e2050; font-size: 10px; letter-spacing: 4px;
           background: transparent; padding: 2px 0; }

/* ─── Page content ─── */
#page_title  { color: #d4aa40; font-size: 18px; font-weight: bold;
               letter-spacing: 2px; background: transparent; }
#section_lbl { color: #4e3e6e; font-size: 10px; letter-spacing: 3px;
               background: transparent; }

/* ─── Cards ─── */
#stat_card { background: #100d1c; border: 1px solid #221840; border-radius: 8px; }
#stat_num  { color: #d4aa40; font-size: 32px; font-weight: bold; background: transparent; }
#stat_lbl  { color: #4e3e6e; font-size: 10px; letter-spacing: 2px; background: transparent; }

/* ─── Inputs ─── */
QLineEdit {
    background: #160e28; border: 1px solid #281840;
    border-radius: 4px; color: #c8b8e8;
    padding: 8px 12px; selection-background-color: #4a0090;
}
QLineEdit:focus { border-color: #6020a8; background: #1a1030; }

/* ─── Status badges ─── */
#st_ok   { background:#071810; border:1px solid #184828; color:#3ac868;
           border-radius:4px; padding:5px 12px; font-size:12px; }
#st_err  { background:#180810; border:1px solid #581020; color:#e05060;
           border-radius:4px; padding:5px 12px; font-size:12px; }
#st_warn { background:#181408; border:1px solid #584010; color:#d4a030;
           border-radius:4px; padding:5px 12px; font-size:12px; }
#st_idle { background:#0c0a18; border:1px solid #1c1530; color:#4e3e6e;
           border-radius:4px; padding:5px 12px; font-size:12px; }

/* ─── Buttons ─── */
#btn_start {
    background:#143a1e; border:1px solid #207038; border-radius:5px;
    color:#46e07e; font-size:13px; font-weight:bold; padding:11px 28px; letter-spacing:1px;
}
#btn_start:hover    { background:#1a5028; border-color:#2ea050; }
#btn_start:disabled { background:#0a1810; border-color:#162618; color:#243c2c; }

#btn_stop {
    background:#3c0810; border:1px solid #8c0a28; border-radius:5px;
    color:#e86880; font-size:13px; font-weight:bold; padding:11px 28px; letter-spacing:1px;
}
#btn_stop:hover    { background:#580c18; border-color:#b01030; }
#btn_stop:disabled { background:#180610; border-color:#280812; color:#3a1820; }

#btn_primary {
    background:#580818; border:1px solid #8c1030; border-radius:4px;
    color:#f0b8c8; font-size:13px; font-weight:bold; padding:9px 22px;
}
#btn_primary:hover { background:#780a22; border-color:#b01838; }

#btn_secondary {
    background:transparent; border:1px solid #2c1c50; border-radius:4px;
    color:#8070b0; font-size:13px; padding:8px 18px;
}
#btn_secondary:hover { background:#160e28; border-color:#5030a0; color:#c8b8e8; }

#btn_danger {
    background:transparent; border:1px solid #380810; border-radius:4px;
    color:#a02840; font-size:12px; padding:6px 14px;
}
#btn_danger:hover { background:#160610; border-color:#780a24; color:#e05070; }

#add_btn {
    background:#580818; border:1px solid #8c1030; border-radius:4px;
    color:#f0b8c8; font-size:20px; font-weight:bold; min-width:40px; max-width:40px;
}
#add_btn:hover { background:#780a22; }

#eye_btn {
    background:#160e28; border:1px solid #281840; border-radius:4px;
    color:#8070b0; font-size:14px; min-width:40px; max-width:40px;
}
#eye_btn:hover { border-color:#5030a0; color:#c8b8e8; }

/* ─── Checkboxes ─── */
QCheckBox { spacing: 10px; }
QCheckBox::indicator {
    width:15px; height:15px;
    border:1px solid #321850; border-radius:3px; background:#160e28;
}
QCheckBox::indicator:hover   { border-color:#6030a8; }
QCheckBox::indicator:checked { background:#6a0a20; border-color:#9a1030; }

/* ─── Scroll ─── */
QScrollArea { background:transparent; border:none; }
QScrollBar:vertical { background:#0a0812; width:5px; margin:0; }
QScrollBar::handle:vertical { background:#281840; border-radius:2px; min-height:24px; }
QScrollBar::handle:vertical:hover { background:#482868; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { height:0; }

/* ─── Channel group header ─── */
#ch_guild_lbl {
    color:#4e3e6e; font-size:9px; letter-spacing:4px;
    padding:10px 0 3px 2px; background:transparent;
}
"""

# ══════════════════════════════════════════════════════════════════════════════
#  HELPER WIDGETS
# ══════════════════════════════════════════════════════════════════════════════

class StatCard(QFrame):
    def __init__(self, num="0", label=""):
        super().__init__()
        self.setObjectName("stat_card")
        vl = QVBoxLayout(self)
        vl.setContentsMargins(20,14,20,14)
        vl.setSpacing(4)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._num = QLabel(num)
        self._num.setObjectName("stat_num")
        self._num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(label)
        lbl.setObjectName("stat_lbl")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self._num)
        vl.addWidget(lbl)

    def set_val(self, n): self._num.setText(str(n))


class KwRow(QWidget):
    removed = pyqtSignal(str)
    def __init__(self, kw: str):
        super().__init__()
        self._kw = kw
        self.setFixedHeight(40)
        self.setStyleSheet(
            "KwRow{background:#160e28;border:1px solid #2e1850;border-radius:4px;}"
        )
        hl = QHBoxLayout(self)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.setSpacing(8)

        dot = QLabel("◆")
        dot.setStyleSheet("color:#6a0a20;font-size:10px;background:transparent;")
        txt = QLabel(kw)
        txt.setStyleSheet("color:#c8b8e8;font-size:13px;background:transparent;")
        rm = QPushButton("✕")
        rm.setFixedSize(22, 22)
        rm.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#4e3e6e;font-size:13px;}"
            "QPushButton:hover{color:#e05070;}")
        rm.clicked.connect(lambda: self.removed.emit(self._kw))
        hl.addWidget(dot); hl.addWidget(txt); hl.addStretch(); hl.addWidget(rm)


class LogEntry(QFrame):
    def __init__(self, e: dict):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            "LogEntry{background:#100d1c;border:1px solid #201840;"
            "border-left:3px solid #4a1870;border-radius:4px;}"
        )
        vl = QVBoxLayout(self)
        vl.setContentsMargins(12, 8, 12, 8)
        vl.setSpacing(4)

        # Top row: keyword badge, channel, timestamp
        top = QHBoxLayout(); top.setSpacing(8)
        kw = QLabel(f" {e['keyword']} ")
        kw.setStyleSheet(
            "color:#d4aa40;background:#201408;border:1px solid #584010;"
            "border-radius:3px;font-size:11px;font-weight:bold;"
        )
        ch = QLabel(f"#{e['channel']}")
        ch.setStyleSheet("color:#9070b8;font-size:11px;background:transparent;")
        gd = QLabel(f"· {e.get('guild','')}")
        gd.setStyleSheet("color:#4e3e6e;font-size:11px;background:transparent;")
        ts = QLabel(f"{e.get('date','')}  {e['ts']}")
        ts.setStyleSheet("color:#3a2c58;font-size:10px;background:transparent;")
        top.addWidget(kw); top.addWidget(ch); top.addWidget(gd)
        top.addStretch(); top.addWidget(ts)

        # Author
        au = QLabel(f"@{e['author']}")
        au.setStyleSheet("color:#c8b8e8;font-size:11px;font-weight:bold;background:transparent;")

        # Content
        cnt = QLabel(e.get("content",""))
        cnt.setWordWrap(True)
        cnt.setStyleSheet("color:#7a6898;font-size:12px;background:transparent;")

        vl.addLayout(top); vl.addWidget(au); vl.addWidget(cnt)


class RecentEntry(QFrame):
    def __init__(self, e: dict):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(36)
        self.setStyleSheet(
            "RecentEntry{background:#0e0b1a;border-left:3px solid #8c0a28;"
            "border-bottom:1px solid #1c1530;}"
        )
        hl = QHBoxLayout(self)
        hl.setContentsMargins(12,0,12,0); hl.setSpacing(10)

        kw = QLabel(f"[{e['keyword']}]")
        kw.setStyleSheet("color:#d4aa40;font-size:11px;font-weight:bold;background:transparent;min-width:80px;")
        ch = QLabel(f"#{e['channel']}")
        ch.setStyleSheet("color:#9070b8;font-size:11px;background:transparent;")
        au = QLabel(f"@{e['author']}")
        au.setStyleSheet("color:#c8b8e8;font-size:11px;background:transparent;")
        ts = QLabel(e['ts'])
        ts.setStyleSheet("color:#3a2c58;font-size:10px;background:transparent;")
        hl.addWidget(kw); hl.addWidget(ch); hl.addWidget(au)
        hl.addStretch(); hl.addWidget(ts)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._bot: BotThread         = None
        self._ch_cbs: dict           = {}   # channel_id -> QCheckBox
        self._kw_rows: dict          = {}   # keyword    -> KwRow
        self._restart_after_stop     = False
        self._nav_btns               = []

        self.setWindowTitle("🔔  Discord Notification Tool")
        self.setMinimumSize(880, 620)
        self.resize(980, 700)
        self._set_dark_titlebar()
        self._set_icon()

        self._build_ui()
        self._populate_from_cfg()

    # ── Platform ──────────────────────────────────────────────────────────────

    def _set_dark_titlebar(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), 20, ctypes.byref(ctypes.c_int(1)), 4)
            except: pass

    def _set_icon(self):
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#8c0a28"))
        p.drawEllipse(1,1,30,30)
        pen = p.pen(); pen.setColor(QColor("#d4aa40")); pen.setWidth(2); p.setPen(pen)
        p.drawLine(16, 5, 16, 27)
        p.drawLine(7, 14, 25, 14)
        p.drawLine(10,10,22,10)
        p.end()
        self.setWindowIcon(QIcon(pix))

    # ── UI build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        hl = QHBoxLayout(root)
        hl.setContentsMargins(0,0,0,0); hl.setSpacing(0)
        hl.addWidget(self._make_sidebar())
        self.stack = QStackedWidget()
        hl.addWidget(self.stack, 1)
        for p in (self._pg_dashboard(), self._pg_channels(),
                  self._pg_keywords(), self._pg_settings(), self._pg_logs()):
            self.stack.addWidget(p)

    def _make_sidebar(self) -> QWidget:
        sb = QWidget(); sb.setObjectName("sidebar"); sb.setFixedWidth(195)
        vl = QVBoxLayout(sb); vl.setContentsMargins(0,0,0,0); vl.setSpacing(0)

        # Logo
        lw = QWidget(); lw.setFixedHeight(80)
        ll = QVBoxLayout(lw); ll.setContentsMargins(18,14,18,6); ll.setSpacing(1)
        sym = QLabel("🔔"); sym.setObjectName("logo_sym")
        txt = QLabel("Notification Tool"); txt.setObjectName("logo_txt")
        ll.addWidget(sym); ll.addWidget(txt)
        vl.addWidget(lw)

        sep0 = QFrame(); sep0.setObjectName("sep")
        sep0.setFrameShape(QFrame.Shape.HLine); sep0.setFixedHeight(1)
        vl.addWidget(sep0)

        for icon, label, idx in [
            ("◈","  Dashboard",  0),
            ("⛩","  Channels",   1),
            ("✦","  Keywords",  2),
            ("⚙","  Settings",    3),
            ("☽","  Logs",   4),
        ]:
            b = QPushButton(f"{icon}{label}")
            b.setObjectName("nav_btn")
            b.setCheckable(True); b.setFixedHeight(48)
            b.clicked.connect(lambda _, i=idx: self._goto(i))
            vl.addWidget(b); self._nav_btns.append(b)
        self._nav_btns[0].setChecked(True)

        vl.addStretch()

        dot = QLabel("· · · · · · · · · · · ·")
        dot.setObjectName("sep_dot"); dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(dot)

        # Status badge at bottom
        self.lbl_st = QLabel("● Not connected")
        self.lbl_st.setObjectName("st_idle")
        self.lbl_st.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_st.setWordWrap(True)
        self.lbl_st.setContentsMargins(8,6,8,6)
        vl.addWidget(self.lbl_st)

        ver = QLabel("v1.0 · Made By Ast")
        ver.setObjectName("ver_lbl"); ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(ver)
        vl.addSpacing(10)
        return sb

    def _goto(self, i: int):
        self.stack.setCurrentIndex(i)
        for j, b in enumerate(self._nav_btns): b.setChecked(j == i)

    # ── Page helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _title(t): l = QLabel(t); l.setObjectName("page_title"); return l

    @staticmethod
    def _sep():
        f = QFrame(); f.setObjectName("sep")
        f.setFrameShape(QFrame.Shape.HLine); f.setFixedHeight(1); return f

    @staticmethod
    def _slbl(t): l = QLabel(t); l.setObjectName("section_lbl"); return l

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _pg_dashboard(self) -> QWidget:
        pg = QWidget()
        vl = QVBoxLayout(pg); vl.setContentsMargins(28,24,28,20); vl.setSpacing(14)

        vl.addWidget(self._title("◈  DASHBOARD"))
        vl.addWidget(self._sep())

        # Bot controls
        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        self.btn_start = QPushButton("▶  Start Bot")
        self.btn_start.setObjectName("btn_start"); self.btn_start.setFixedHeight(44)
        self.btn_start.clicked.connect(self._bot_start)
        self.btn_stop = QPushButton("■  Stop Bot")
        self.btn_stop.setObjectName("btn_stop"); self.btn_stop.setFixedHeight(44)
        self.btn_stop.setEnabled(False); self.btn_stop.clicked.connect(self._bot_stop)
        ctrl.addWidget(self.btn_start); ctrl.addWidget(self.btn_stop); ctrl.addStretch()
        vl.addLayout(ctrl)

        # Stat cards
        sr = QHBoxLayout(); sr.setSpacing(12)
        self.sc_ch  = StatCard("0", "WATCHED CHANNELS")
        self.sc_kw  = StatCard("0", "KEYWORDS")
        self.sc_hit = StatCard("0", "DETECTIONS")
        for sc in (self.sc_ch, self.sc_kw, self.sc_hit): sr.addWidget(sc)
        vl.addLayout(sr)

        # Bot activity indicator
        self._lbl_activity = QLabel("○  Waiting for messages…")
        self._lbl_activity.setStyleSheet(
            "color:#2e2050;font-size:11px;background:transparent;padding:2px 0;")
        vl.addWidget(self._lbl_activity)

        # Recent activity
        rl = QLabel("· · ·  RECENT ACTIVITY  · · ·"); rl.setObjectName("section_lbl")
        rl.setAlignment(Qt.AlignmentFlag.AlignCenter); vl.addWidget(rl)

        self._recent_w = QWidget()
        self._recent_l = QVBoxLayout(self._recent_w)
        self._recent_l.setContentsMargins(0,0,0,0); self._recent_l.setSpacing(2)
        self._recent_l.setAlignment(Qt.AlignmentFlag.AlignTop)

        empty_lbl = QLabel("No detections yet.")
        empty_lbl.setStyleSheet("color:#2e2050;font-size:12px;padding:20px;background:transparent;")
        empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recent_l.addWidget(empty_lbl)
        self._recent_empty = empty_lbl

        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(self._recent_w)
        sa.setFixedHeight(210)
        border_frame = QFrame()
        border_frame.setStyleSheet("QFrame{border:1px solid #1c1530;border-radius:4px;}")
        bfl = QVBoxLayout(border_frame); bfl.setContentsMargins(0,0,0,0)
        bfl.addWidget(sa); vl.addWidget(border_frame)

        vl.addStretch()
        return pg

    # ── Channels ──────────────────────────────────────────────────────────────

    def _pg_channels(self) -> QWidget:
        pg = QWidget()
        vl = QVBoxLayout(pg); vl.setContentsMargins(28,24,28,20); vl.setSpacing(14)

        top = QHBoxLayout()
        top.addWidget(self._title("⛩  CHANNELS")); top.addStretch()
        bs = QPushButton("✓  Save Selection"); bs.setObjectName("btn_primary")
        bs.setFixedHeight(38); bs.clicked.connect(self._ch_save)
        top.addWidget(bs); vl.addLayout(top)
        vl.addWidget(self._sep())

        self._ch_info = QLabel(
            "🔔  Start the bot from Dashboard to list channels."
            "All text channels from your servers will appear here once connected."
        )
        self._ch_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ch_info.setStyleSheet(
            "color:#3a2c58;font-size:13px;padding:40px 0;background:transparent;")
        vl.addWidget(self._ch_info)

        self._ch_inner = QWidget()
        self._ch_inner_l = QVBoxLayout(self._ch_inner)
        self._ch_inner_l.setContentsMargins(4,4,4,4); self._ch_inner_l.setSpacing(3)
        self._ch_inner_l.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._ch_scroll = QScrollArea(); self._ch_scroll.setWidgetResizable(True)
        self._ch_scroll.setWidget(self._ch_inner); self._ch_scroll.hide()

        border = QFrame()
        border.setStyleSheet("QFrame{border:1px solid #1c1530;border-radius:4px;}")
        bfl = QVBoxLayout(border); bfl.setContentsMargins(0,0,0,0)
        bfl.addWidget(self._ch_scroll)
        vl.addWidget(border)
        vl.addStretch()
        return pg

    # ── Keywords ──────────────────────────────────────────────────────────────

    def _pg_keywords(self) -> QWidget:
        pg = QWidget()
        vl = QVBoxLayout(pg); vl.setContentsMargins(28,24,28,20); vl.setSpacing(14)

        vl.addWidget(self._title("✦  KEYWORDS"))
        vl.addWidget(self._sep())

        ir = QHBoxLayout(); ir.setSpacing(8)
        self._kw_inp = QLineEdit()
        self._kw_inp.setPlaceholderText("Add a new word or phrase…")
        self._kw_inp.setFixedHeight(42); self._kw_inp.returnPressed.connect(self._kw_add)
        add = QPushButton("+"); add.setObjectName("add_btn")
        add.setFixedHeight(42); add.clicked.connect(self._kw_add)
        ir.addWidget(self._kw_inp); ir.addWidget(add)
        vl.addLayout(ir)

        vl.addWidget(self._slbl("· · ·  ACTIVE KEYWORDS  · · ·"))

        self._kw_inner = QWidget()
        self._kw_inner_l = QVBoxLayout(self._kw_inner)
        self._kw_inner_l.setContentsMargins(0,0,0,0); self._kw_inner_l.setSpacing(6)
        self._kw_inner_l.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._kw_empty = QLabel("No keywords added yet.")
        self._kw_empty.setStyleSheet("color:#2e2050;font-size:12px;padding:20px;background:transparent;")
        self._kw_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kw_inner_l.addWidget(self._kw_empty)

        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(self._kw_inner)
        border = QFrame()
        border.setStyleSheet("QFrame{border:1px solid #1c1530;border-radius:4px;}")
        bfl = QVBoxLayout(border); bfl.setContentsMargins(0,0,0,0); bfl.addWidget(sa)
        vl.addWidget(border)
        return pg

    # ── Settings ──────────────────────────────────────────────────────────────

    def _pg_settings(self) -> QWidget:
        pg = QWidget()
        vl = QVBoxLayout(pg); vl.setContentsMargins(28,24,28,20); vl.setSpacing(14)

        vl.addWidget(self._title("⚙  SETTINGS"))
        vl.addWidget(self._sep())

        # Discord token
        vl.addWidget(self._slbl("· · ·  DISCORD BOT TOKEN  · · ·"))
        tr = QHBoxLayout(); tr.setSpacing(8)
        self._tok = QLineEdit()
        self._tok.setPlaceholderText("Paste your bot token here")
        self._tok.setEchoMode(QLineEdit.EchoMode.Password); self._tok.setFixedHeight(42)
        eye = QPushButton("👁"); eye.setObjectName("eye_btn")
        eye.setFixedHeight(42); eye.setCheckable(True)
        eye.toggled.connect(lambda v: self._tok.setEchoMode(
            QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password))
        tr.addWidget(self._tok); tr.addWidget(eye); vl.addLayout(tr)

        tok_hint = QLabel("→  discord.com/developers  ·  Bot tab  ·  Copy token")
        tok_hint.setStyleSheet("color:#3a2c58;font-size:11px;background:transparent;")
        tok_hint.setContentsMargins(0,0,0,4); vl.addWidget(tok_hint)

        # ntfy
        vl.addWidget(self._sep())
        vl.addWidget(self._slbl("· · ·  NTFY NOTIFICATION URL  · · ·"))

        self._ntfy_url = QLineEdit()
        self._ntfy_url.setPlaceholderText("https://ntfy.sh/your-topic-name")
        self._ntfy_url.setFixedHeight(42); vl.addWidget(self._ntfy_url)

        hint = QLabel(
            "📱  Install the ntfy app on your phone and subscribe to the same URL."
            "  ·  Example: https://ntfy.sh/my-channel-xyz"
        )
        hint.setStyleSheet("color:#3a2c58;font-size:11px;background:transparent;line-height:1.5;")
        vl.addWidget(hint)

        vl.addWidget(self._sep())
        br = QHBoxLayout(); br.setSpacing(10)
        sv = QPushButton("⚔  Save & Apply"); sv.setObjectName("btn_primary")
        sv.setFixedHeight(44); sv.clicked.connect(self._settings_save)
        tt = QPushButton("🔔  Send Test Notification"); tt.setObjectName("btn_secondary")
        tt.setFixedHeight(44); tt.clicked.connect(self._settings_test)
        br.addWidget(sv); br.addWidget(tt); br.addStretch(); vl.addLayout(br)
        vl.addStretch()
        return pg

    # ── Logs ──────────────────────────────────────────────────────────────────

    def _pg_logs(self) -> QWidget:
        pg = QWidget()
        vl = QVBoxLayout(pg); vl.setContentsMargins(28,24,28,20); vl.setSpacing(14)

        top = QHBoxLayout()
        top.addWidget(self._title("☽  LOGS")); top.addStretch()
        cl = QPushButton("✕  Clear All"); cl.setObjectName("btn_danger")
        cl.setFixedHeight(36); cl.clicked.connect(self._logs_clear)
        top.addWidget(cl); vl.addLayout(top)
        vl.addWidget(self._sep())

        self._log_inner = QWidget()
        self._log_inner_l = QVBoxLayout(self._log_inner)
        self._log_inner_l.setContentsMargins(0,0,0,0); self._log_inner_l.setSpacing(6)
        self._log_inner_l.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._log_empty = QLabel("No logs yet. Start the bot, select channels and add keywords to see detections here.")
        self._log_empty.setStyleSheet("color:#2e2050;font-size:13px;padding:40px 20px;background:transparent;")
        self._log_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._log_empty.setWordWrap(True)
        self._log_inner_l.addWidget(self._log_empty)

        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(self._log_inner)
        border = QFrame()
        border.setStyleSheet("QFrame{border:1px solid #1c1530;border-radius:4px;}")
        bfl = QVBoxLayout(border); bfl.setContentsMargins(0,0,0,0); bfl.addWidget(sa)
        vl.addWidget(border)
        return pg

    # ── Populate from config ──────────────────────────────────────────────────

    def _populate_from_cfg(self):
        c = load_cfg()
        self._tok.setText(c.get("token",""))
        self._ntfy_url.setText(c.get("ntfy_url",""))
        for kw in c.get("keywords",[]): self._kw_add_item(kw)
        for e in c.get("logs",[])[:80]: self._log_add(e, top=False)
        self._update_stats()

    # ── Stats ──────────────────────────────────────────────────────────────────

    def _update_stats(self):
        c = load_cfg()
        self.sc_ch.set_val(len(c.get("watched_channels",[])))
        self.sc_kw.set_val(len(c.get("keywords",[])))
        self.sc_hit.set_val(len(c.get("logs",[])))

    # ── Status badge ──────────────────────────────────────────────────────────

    def _set_status(self, msg: str, level: str):
        self.lbl_st.setText(msg)
        self.lbl_st.setObjectName(f"st_{level}")
        self.lbl_st.style().unpolish(self.lbl_st)
        self.lbl_st.style().polish(self.lbl_st)

    # ── Bot control ───────────────────────────────────────────────────────────

    def _bot_start(self):
        c = load_cfg()
        tok = c.get("token","").strip()
        if not tok:
            self._goto(3)
            self._set_status("⚠  No token entered", "warn"); return
        if self._bot and self._bot.isRunning(): return
        self._bot = BotThread(tok)
        self._bot.sig_ch.connect(self._on_channels)
        self._bot.sig_hit.connect(self._on_detection)
        self._bot.sig_st.connect(self._on_status)
        self._bot.sig_activity.connect(self._on_activity)
        self._bot.start()
        self._set_status("⏳  Connecting…", "warn")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _bot_stop(self):
        if not (self._bot and self._bot.isRunning()): return
        self.btn_start.setEnabled(False); self.btn_stop.setEnabled(False)
        self._set_status("⏳  Stopping…", "warn")
        old = self._bot; self._bot = None
        old.finished.connect(self._after_stop)
        threading.Thread(target=old.stop, daemon=True).start()

    def _after_stop(self):
        self._set_status("● Not connected", "idle")
        self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)
        if self._restart_after_stop:
            self._restart_after_stop = False
            QTimer.singleShot(400, self._bot_start)

    def _on_status(self, msg: str, level: str):
        self._set_status(msg, level)
        if level == "err":
            self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)

    def _on_activity(self, info: str):
        self._lbl_activity.setText(f"●  Message in watched channel: {info}")
        self._lbl_activity.setStyleSheet(
            "color:#4a3a6e;font-size:11px;background:transparent;padding:2px 0;")
        # Dim after 4 seconds
        QTimer.singleShot(4000, lambda: self._lbl_activity.setStyleSheet(
            "color:#2e2050;font-size:11px;background:transparent;padding:2px 0;"))

    # ── Channel slot ──────────────────────────────────────────────────────────

    def _on_channels(self, chs: list):
        self._ch_cbs.clear()
        while self._ch_inner_l.count():
            w = self._ch_inner_l.takeAt(0).widget()
            if w: w.deleteLater()

        cfg = load_cfg()
        watched = set(cfg.get("watched_channels",[]))
        cur_guild = None

        for ch in sorted(chs, key=lambda x: (x["guild"].lower(), x["name"])):
            if ch["guild"] != cur_guild:
                cur_guild = ch["guild"]
                gl = QLabel(f"◈  {cur_guild.upper()}")
                gl.setObjectName("ch_guild_lbl")
                gl.setStyleSheet(
                    "color:#4e3e6e;font-size:9px;letter-spacing:4px;"
                    "padding:10px 6px 3px 6px;background:transparent;"
                )
                self._ch_inner_l.addWidget(gl)

            cb = QCheckBox(f"  # {ch['name']}")
            cb.setChecked(ch["id"] in watched)
            cb.setContentsMargins(20,0,0,0)
            self._ch_cbs[ch["id"]] = cb
            self._ch_inner_l.addWidget(cb)

        self._ch_info.hide(); self._ch_scroll.show()
        self._update_stats()

    # ── Detection slot ────────────────────────────────────────────────────────

    def _on_detection(self, e: dict):
        # Remove "no detections yet" label
        if self._recent_empty and self._recent_empty.isVisible():
            self._recent_empty.hide()

        # Recent list (keep max 7)
        while self._recent_l.count() > 7:
            w = self._recent_l.takeAt(self._recent_l.count()-1).widget()
            if w: w.deleteLater()

        self._recent_l.insertWidget(0, RecentEntry(e))
        self._log_add(e, top=True)
        self._update_stats()

    # ── Channel save ──────────────────────────────────────────────────────────

    def _ch_save(self):
        watched = [cid for cid, cb in self._ch_cbs.items() if cb.isChecked()]
        c = load_cfg(); c["watched_channels"] = watched; save_cfg(c)
        self._update_stats()
        self._set_status(f"✓  {len(watched)} channels saved", "ok")

    # ── Keyword ops ───────────────────────────────────────────────────────────

    def _kw_add(self):
        kw = self._kw_inp.text().strip()
        if not kw or kw in self._kw_rows: return
        self._kw_inp.clear()
        self._kw_add_item(kw)
        c = load_cfg(); kws = c.setdefault("keywords",[])
        if kw not in kws: kws.append(kw); save_cfg(c)
        self._update_stats()

    def _kw_add_item(self, kw: str):
        if self._kw_empty: self._kw_empty.hide()
        row = KwRow(kw); row.removed.connect(self._kw_remove)
        self._kw_rows[kw] = row
        self._kw_inner_l.addWidget(row)

    def _kw_remove(self, kw: str):
        row = self._kw_rows.pop(kw, None)
        if row: row.deleteLater()
        if not self._kw_rows and self._kw_empty:
            self._kw_empty.show()
        c = load_cfg(); kws = c.get("keywords",[])
        if kw in kws: kws.remove(kw); save_cfg(c)
        self._update_stats()

    # ── Settings ops ──────────────────────────────────────────────────────────

    def _settings_save(self):
        c = load_cfg()
        c["token"]       = self._tok.text().strip()
        c["ntfy_url"] = self._ntfy_url.text().strip()
        save_cfg(c)
        if self._bot and self._bot.isRunning():
            self._restart_after_stop = True
            self._bot_stop()
        else:
            self._set_status("✓  Settings saved", "ok")

    def _settings_test(self):
        url = self._ntfy_url.text().strip()
        if not url:
            self._set_status("⚠  ntfy URL is empty — Enter a URL", "warn")
            return
        try:
            r = requests.post(
                url,
                data="Discord Notification Tool is up and running!".encode("utf-8"),
                headers={
                    "Title":    "Notification",
                    "Priority": "4",
                    "Tags":     "bell",
                },
                timeout=8
            )
            if r.ok:
                self._set_status("✓  Test notification sent!", "ok")
            else:
                self._set_status(f"✕  Server response: HTTP {r.status_code} — Check the URL", "err")
        except requests.exceptions.ConnectionError:
            self._set_status("✕  Connection failed — Check your internet connection", "err")
        except requests.exceptions.Timeout:
            self._set_status("✕  Timeout (8s) — server not responding", "err")
        except Exception as e:
            self._set_status(f"✕  Hata: {str(e)[:60]}", "err")

    # ── Log ops ───────────────────────────────────────────────────────────────

    def _log_add(self, e: dict, top: bool = True):
        if self._log_empty: self._log_empty.hide()
        entry = LogEntry(e)
        if top: self._log_inner_l.insertWidget(0, entry)
        else:   self._log_inner_l.addWidget(entry)

    def _logs_clear(self):
        while self._log_inner_l.count():
            w = self._log_inner_l.takeAt(0).widget()
            if w: w.deleteLater()
        if self._log_empty: self._log_empty.show()
        c = load_cfg(); c["logs"] = []; save_cfg(c)
        self._update_stats()

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._bot:
            self._bot._dead = True
            if self._bot._cli and self._bot._loop and not self._bot._loop.is_closed():
                fut = asyncio.run_coroutine_threadsafe(
                    self._bot._cli.close(), self._bot._loop)
                try: fut.result(timeout=3)
                except: pass
        event.accept()

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor("#0c0a12"))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor("#c8b8e8"))
    pal.setColor(QPalette.ColorRole.Base,            QColor("#160e28"))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor("#100d1c"))
    pal.setColor(QPalette.ColorRole.Text,            QColor("#c8b8e8"))
    pal.setColor(QPalette.ColorRole.Button,          QColor("#160e28"))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor("#c8b8e8"))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor("#4a0090"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#f0e8ff"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

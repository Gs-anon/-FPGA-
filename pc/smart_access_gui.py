import contextlib
import csv
import io
import threading
import time

from datetime import datetime
from pathlib import Path

import tkinter as tk

from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog

import cv2
import serial

from serial.tools import list_ports

from PIL import Image
from PIL import ImageTk

import send_image

from user_db import UserDatabase
from user_db import MAX_USERS

from access_log import AccessLogger
from system_config import SystemConfig

from multi_user_client import MultiUserFPGAClient


# ============================================================
# Authentication modes
# ============================================================

AUTH_MODE_NAMES = {

    0:
        "PASSWORD_ONLY",

    1:
        "FACE_ONLY",

    2:
        "FACE_AND_PASSWORD"

}


MODE_NAME_TO_VALUE = {

    "PASSWORD_ONLY":
        0,

    "FACE_ONLY":
        1,

    "FACE_AND_PASSWORD":
        2

}


# ============================================================
# Main GUI
# ============================================================

class SmartAccessGUI:


    def __init__(
        self,
        root
    ):

        self.root = root


        self.root.title(
            "EG4S20 多用户智能门禁上位机 V3.0"
        )


        self.root.geometry(
            "1240x840"
        )


        self.root.minsize(
            1100,
            650
        )


        # ====================================================
        # Persistent PC data
        # ====================================================

        self.db = UserDatabase(
            "users.json"
        )


        self.logger = AccessLogger(
            "access_log.csv"
        )


        self.config = SystemConfig(
            "system_config.json"
        )


        # ====================================================
        # Serial
        # ====================================================

        self.ser = None

        self.client = None


        self.serial_lock = threading.Lock()


        self.operation_busy = False


        # ====================================================
        # FPGA runtime
        # ====================================================

        self.last_fpga_status = None


        self.runtime_users = {

            user_id:
                None

            for user_id
            in range(
                MAX_USERS
            )

        }


        # ====================================================
        # Reset detection
        # ====================================================

        self.status_poll_count = 0


        self.reset_restore_pending = False


        # ====================================================
        # Camera
        # ====================================================

        self.camera = None

        self.camera_running = False


        self.live_face_pixels = None


        self.captured_face_pixels = None

        self.captured_face_pil = None


        self.camera_photo = None

        self.face_photo = None


        # ====================================================
        # Frame ID
        # ====================================================

        self.frame_id = 1


        # ====================================================
        # Automatic recognition
        # ====================================================

        self.auto_face_stable_count = 0

        self.auto_absent_count = 0


        self.auto_rearm_absent_frames = 8


        self.auto_armed = True


        self.auto_last_trigger_time = 0.0


        # ====================================================
        # Face detector
        # ====================================================

        cascade_path = (

            cv2.data.haarcascades
            +
            "haarcascade_frontalface_default.xml"

        )


        self.face_detector = cv2.CascadeClassifier(
            cascade_path
        )


        if self.face_detector.empty():

            raise RuntimeError(
                "OpenCV Haar face detector could not be loaded"
            )


        # ====================================================
        # GUI
        # ====================================================

        self._build_ui()


        self._refresh_ports()

        self._refresh_user_table()

        self._refresh_log_table()


        self.root.protocol(

            "WM_DELETE_WINDOW",

            self._on_close

        )


        self.root.after(

            800,

            self._auto_status_tick

        )


    # ========================================================
    # Build UI
    # ========================================================

    def _build_ui(
        self
    ):

        outer = ttk.Frame(

            self.root,

            padding=8

        )


        outer.pack(

            fill="both",

            expand=True

        )


        # ====================================================
        # TOP
        # ====================================================

        connection = ttk.LabelFrame(

            outer,

            text="串口 / FPGA",

            padding=8

        )


        connection.pack(
            fill="x"
        )


        ttk.Label(

            connection,

            text="串口:"

        ).pack(
            side="left"
        )


        self.port_var = tk.StringVar()


        self.port_combo = ttk.Combobox(

            connection,

            width=12,

            state="readonly",

            textvariable=self.port_var

        )


        self.port_combo.pack(

            side="left",

            padx=5

        )


        ttk.Button(

            connection,

            text="刷新串口",

            command=self._refresh_ports

        ).pack(

            side="left",

            padx=3

        )


        self.connect_button = ttk.Button(

            connection,

            text="连接",

            command=self._toggle_connection

        )


        self.connect_button.pack(

            side="left",

            padx=3

        )


        self.connection_var = tk.StringVar(
            value="未连接"
        )


        ttk.Label(

            connection,

            textvariable=self.connection_var

        ).pack(

            side="left",

            padx=10

        )


        ttk.Separator(

            connection,

            orient="vertical"

        ).pack(

            side="left",

            fill="y",

            padx=8

        )


        # ====================================================
        # Mode
        # ====================================================

        ttk.Label(

            connection,

            text="认证模式:"

        ).pack(
            side="left"
        )


        saved_mode = self.config.get(
            "auth_mode",
            0
        )


        self.auth_mode_var = tk.StringVar(

            value=AUTH_MODE_NAMES.get(
                saved_mode,
                "PASSWORD_ONLY"
            )

        )


        self.auth_mode_combo = ttk.Combobox(

            connection,

            width=20,

            state="readonly",

            textvariable=self.auth_mode_var,

            values=list(
                MODE_NAME_TO_VALUE.keys()
            )

        )


        self.auth_mode_combo.pack(

            side="left",

            padx=5

        )


        ttk.Button(

            connection,

            text="写入模式",

            command=self._set_auth_mode

        ).pack(

            side="left",

            padx=3

        )


        # ====================================================
        # Threshold
        # ====================================================

        ttk.Label(

            connection,

            text="阈值:"

        ).pack(

            side="left",

            padx=(
                10,
                0
            )

        )


        saved_threshold = self.config.get(
            "match_threshold"
        )


        self.threshold_var = tk.StringVar(

            value=(

                ""

                if saved_threshold is None

                else

                str(
                    saved_threshold
                )

            )

        )


        ttk.Entry(

            connection,

            width=7,

            textvariable=self.threshold_var

        ).pack(

            side="left",

            padx=5

        )


        ttk.Button(

            connection,

            text="写入阈值",

            command=self._set_threshold

        ).pack(

            side="left",

            padx=3

        )


        ttk.Button(

            connection,

            text="远程开门",

            command=self._remote_open

        ).pack(

            side="right",

            padx=3

        )


        # ====================================================
        # MAIN
        # ====================================================

        upper = ttk.Frame(
            outer
        )


        upper.pack(

            fill="both",

            expand=True,

            pady=(
                8,
                0
            )

        )


        # ====================================================
        # CAMERA
        # ====================================================

        camera_frame = ttk.LabelFrame(

            upper,

            text="摄像头 / 人脸采集",

            padding=8

        )


        camera_frame.pack(

            side="left",

            fill="both",

            expand=True,

            padx=(
                0,
                5
            )

        )


        self.camera_label = ttk.Label(

            camera_frame,

            anchor="center"

        )


        self.camera_label.pack(

            fill="both",

            expand=True

        )


        camera_controls = ttk.Frame(
            camera_frame
        )


        camera_controls.pack(

            fill="x",

            pady=(
                8,
                0
            )

        )


        ttk.Label(

            camera_controls,

            text="Camera:"

        ).pack(
            side="left"
        )


        self.camera_index_var = tk.IntVar(

            value=self.config.get(
                "camera_index",
                0
            )

        )


        ttk.Spinbox(

            camera_controls,

            from_=0,

            to=9,

            width=4,

            textvariable=self.camera_index_var

        ).pack(

            side="left",

            padx=5

        )


        self.camera_button = ttk.Button(

            camera_controls,

            text="启动摄像头",

            command=self._toggle_camera

        )


        self.camera_button.pack(

            side="left",

            padx=3

        )


        ttk.Button(

            camera_controls,

            text="采集当前人脸",

            command=self._capture_face

        ).pack(

            side="left",

            padx=3

        )


        self.face_state_var = tk.StringVar(
            value="未检测到人脸"
        )


        ttk.Label(

            camera_controls,

            textvariable=self.face_state_var

        ).pack(

            side="left",

            padx=10

        )


        # ====================================================
        # SCROLLABLE RIGHT
        # ====================================================

        self.right_container = ttk.Frame(

            upper,

            width=470

        )


        self.right_container.pack(

            side="right",

            fill="y",

            padx=(
                5,
                0
            )

        )


        self.right_container.pack_propagate(
            False
        )


        self.right_canvas = tk.Canvas(

            self.right_container,

            highlightthickness=0,

            borderwidth=0

        )


        self.right_scrollbar = ttk.Scrollbar(

            self.right_container,

            orient="vertical",

            command=self.right_canvas.yview

        )


        self.right_canvas.configure(

            yscrollcommand=
                self.right_scrollbar.set

        )


        self.right_scrollbar.pack(

            side="right",

            fill="y"

        )


        self.right_canvas.pack(

            side="left",

            fill="both",

            expand=True

        )


        right = ttk.Frame(
            self.right_canvas
        )


        self.right_canvas_window = (

            self.right_canvas.create_window(

                (
                    0,
                    0
                ),

                window=right,

                anchor="nw"

            )

        )


        def right_content_configure(
            _event
        ):

            bbox = self.right_canvas.bbox(
                "all"
            )


            if bbox is not None:

                self.right_canvas.configure(
                    scrollregion=bbox
                )


        right.bind(

            "<Configure>",

            right_content_configure

        )


        def right_canvas_configure(
            event
        ):

            self.right_canvas.itemconfigure(

                self.right_canvas_window,

                width=event.width

            )


        self.right_canvas.bind(

            "<Configure>",

            right_canvas_configure

        )


        self.root.bind_all(

            "<MouseWheel>",

            self._right_mousewheel,

            add="+"

        )


        self.root.bind_all(

            "<Button-4>",

            self._right_linux_scroll_up,

            add="+"

        )


        self.root.bind_all(

            "<Button-5>",

            self._right_linux_scroll_down,

            add="+"

        )


        # ====================================================
        # FACE PREVIEW
        # ====================================================

        preview_frame = ttk.LabelFrame(

            right,

            text="已采集 64×64 Gray8",

            padding=8

        )


        preview_frame.pack(
            fill="x"
        )


        self.face_preview_label = ttk.Label(

            preview_frame,

            anchor="center"

        )


        self.face_preview_label.pack(
            fill="x"
        )


        # ====================================================
        # MANUAL RECOGNITION
        # ====================================================

        action_frame = ttk.LabelFrame(

            right,

            text="人脸操作",

            padding=8

        )


        action_frame.pack(

            fill="x",

            pady=(
                8,
                0
            )

        )


        ttk.Label(

            action_frame,

            text=(
                "注册操作使用下方用户表中当前选中的用户。"
            )

        ).pack(
            anchor="w"
        )


        ttk.Button(

            action_frame,

            text="将当前人脸注册到选中用户",

            command=self._enroll_selected_user

        ).pack(

            fill="x",

            pady=(
                6,
                2
            )

        )


        ttk.Button(

            action_frame,

            text="识别当前人脸",

            command=self._recognize_captured_face

        ).pack(

            fill="x",

            pady=2

        )


        self.result_var = tk.StringVar(
            value="尚未识别"
        )


        ttk.Label(

            action_frame,

            textvariable=self.result_var,

            wraplength=410,

            justify="left"

        ).pack(

            fill="x",

            pady=(
                8,
                0
            )

        )


        # ====================================================
        # AUTO ACCESS
        # ====================================================

        auto_frame = ttk.LabelFrame(

            right,

            text="自动门禁",

            padding=8

        )


        auto_frame.pack(

            fill="x",

            pady=(
                8,
                0
            )

        )


        self.auto_enabled_var = tk.BooleanVar(

            value=self.config.get(
                "auto_recognition",
                False
            )

        )


        ttk.Checkbutton(

            auto_frame,

            text="启用自动识别",

            variable=self.auto_enabled_var,

            command=self._on_auto_toggle

        ).grid(

            row=0,

            column=0,

            columnspan=5,

            sticky="w"

        )


        ttk.Label(

            auto_frame,

            text="稳定帧数:"

        ).grid(

            row=1,

            column=0,

            sticky="w",

            pady=5

        )


        self.auto_stable_frames_var = tk.IntVar(

            value=self.config.get(
                "auto_stable_frames",
                8
            )

        )


        ttk.Spinbox(

            auto_frame,

            from_=3,

            to=60,

            width=6,

            textvariable=self.auto_stable_frames_var

        ).grid(

            row=1,

            column=1,

            padx=5,

            sticky="w"

        )


        ttk.Label(

            auto_frame,

            text="冷却:"

        ).grid(

            row=1,

            column=2,

            sticky="w"

        )


        self.auto_cooldown_var = tk.StringVar(

            value=str(
                self.config.get(
                    "auto_cooldown_seconds",
                    5.0
                )
            )

        )


        ttk.Spinbox(

            auto_frame,

            from_=1.0,

            to=60.0,

            increment=0.5,

            width=6,

            textvariable=self.auto_cooldown_var

        ).grid(

            row=1,

            column=3,

            padx=5,

            sticky="w"

        )


        ttk.Label(

            auto_frame,

            text="秒"

        ).grid(

            row=1,

            column=4,

            sticky="w"

        )


        self.auto_state_var = tk.StringVar(

            value=(
                "自动识别已启用"
                if self.auto_enabled_var.get()
                else
                "自动识别关闭"
            )

        )


        ttk.Label(

            auto_frame,

            textvariable=self.auto_state_var,

            wraplength=410,

            justify="left"

        ).grid(

            row=2,

            column=0,

            columnspan=5,

            sticky="w",

            pady=(
                5,
                0
            )

        )


        # ====================================================
        # RESTORE
        # ====================================================

        restore_frame = ttk.LabelFrame(

            right,

            text="系统启动 / FPGA复位恢复",

            padding=8

        )


        restore_frame.pack(

            fill="x",

            pady=(
                8,
                0
            )

        )


        self.auto_restore_var = tk.BooleanVar(

            value=self.config.get(
                "auto_restore_on_connect",
                True
            )

        )


        ttk.Checkbutton(

            restore_frame,

            text="连接或检测到FPGA复位后自动恢复",

            variable=self.auto_restore_var,

            command=self._on_auto_restore_toggle

        ).pack(
            anchor="w"
        )


        ttk.Button(

            restore_frame,

            text="立即恢复 FPGA 运行状态",

            command=self._manual_restore_fpga

        ).pack(

            fill="x",

            pady=(
                6,
                4
            )

        )


        self.restore_state_var = tk.StringVar(
            value="尚未执行恢复"
        )


        ttk.Label(

            restore_frame,

            textvariable=self.restore_state_var,

            wraplength=410,

            justify="left"

        ).pack(
            anchor="w"
        )


        # ====================================================
        # STATUS
        # ====================================================

        status_frame = ttk.LabelFrame(

            right,

            text="系统状态",

            padding=8

        )


        status_frame.pack(

            fill="x",

            pady=(
                8,
                0
            )

        )


        self.status_door_var = tk.StringVar(
            value="Door: --"
        )


        self.status_lockout_var = tk.StringVar(
            value="Lockout: --"
        )


        self.status_mode_var = tk.StringVar(
            value="Mode: --"
        )


        ttk.Label(

            status_frame,

            textvariable=self.status_door_var

        ).grid(

            row=0,

            column=0,

            sticky="w"

        )


        ttk.Label(

            status_frame,

            textvariable=self.status_lockout_var

        ).grid(

            row=1,

            column=0,

            sticky="w"

        )


        ttk.Label(

            status_frame,

            textvariable=self.status_mode_var

        ).grid(

            row=2,

            column=0,

            sticky="w"

        )


        ttk.Button(

            status_frame,

            text="刷新状态",

            command=self._manual_refresh_status

        ).grid(

            row=0,

            column=1,

            rowspan=3,

            padx=10

        )


        # ====================================================
        # DYNAMIC USER MANAGEMENT
        # ====================================================

        users_frame = ttk.LabelFrame(

            right,

            text="动态用户管理",

            padding=8

        )


        users_frame.pack(

            fill="x",

            pady=(
                8,
                10
            )

        )


        self.user_capacity_var = tk.StringVar()


        ttk.Label(

            users_frame,

            textvariable=self.user_capacity_var

        ).pack(

            anchor="w",

            pady=(
                0,
                5
            )

        )


        columns = (

            "id",
            "name",
            "pc",
            "fpga",
            "template"

        )


        self.user_tree = ttk.Treeview(

            users_frame,

            columns=columns,

            show="headings",

            height=8,

            selectmode="browse"

        )


        self.user_tree.heading(
            "id",
            text="ID"
        )


        self.user_tree.heading(
            "name",
            text="姓名"
        )


        self.user_tree.heading(
            "pc",
            text="PC权限"
        )


        self.user_tree.heading(
            "fpga",
            text="FPGA"
        )


        self.user_tree.heading(
            "template",
            text="模板"
        )


        self.user_tree.column(

            "id",

            width=35,

            anchor="center"

        )


        self.user_tree.column(

            "name",

            width=120

        )


        self.user_tree.column(

            "pc",

            width=65,

            anchor="center"

        )


        self.user_tree.column(

            "fpga",

            width=65,

            anchor="center"

        )


        self.user_tree.column(

            "template",

            width=80,

            anchor="center"

        )


        self.user_tree.pack(
            fill="x"
        )


        user_buttons_1 = ttk.Frame(
            users_frame
        )


        user_buttons_1.pack(

            fill="x",

            pady=(
                6,
                2
            )

        )


        ttk.Button(

            user_buttons_1,

            text="添加用户",

            command=self._add_user

        ).pack(

            side="left",

            padx=2

        )


        ttk.Button(

            user_buttons_1,

            text="删除用户",

            command=self._delete_user

        ).pack(

            side="left",

            padx=2

        )


        ttk.Button(

            user_buttons_1,

            text="改名",

            command=self._rename_user

        ).pack(

            side="left",

            padx=2

        )


        ttk.Button(

            user_buttons_1,

            text="切换PC权限",

            command=self._toggle_pc_permission

        ).pack(

            side="left",

            padx=2

        )


        user_buttons_2 = ttk.Frame(
            users_frame
        )


        user_buttons_2.pack(

            fill="x",

            pady=2

        )


        ttk.Button(

            user_buttons_2,

            text="同步全部权限→FPGA",

            command=self._sync_permissions

        ).pack(

            side="left",

            padx=2

        )


        ttk.Button(

            user_buttons_2,

            text="查询FPGA用户状态",

            command=self._refresh_fpga_users

        ).pack(

            side="left",

            padx=2

        )


        # ====================================================
        # LOG
        # ====================================================

        log_frame = ttk.LabelFrame(

            outer,

            text="最近访问日志",

            padding=8

        )


        log_frame.pack(

            fill="both",

            pady=(
                8,
                0
            )

        )


        log_columns = (

            "timestamp",
            "name",
            "recognized",
            "authorized",
            "best",
            "mode",
            "result"

        )


        self.log_tree = ttk.Treeview(

            log_frame,

            columns=log_columns,

            show="headings",

            height=8

        )


        headings = {

            "timestamp":
                "时间",

            "name":
                "用户",

            "recognized":
                "识别",

            "authorized":
                "权限",

            "best":
                "Best",

            "mode":
                "模式",

            "result":
                "结果"

        }


        widths = {

            "timestamp":
                145,

            "name":
                110,

            "recognized":
                55,

            "authorized":
                55,

            "best":
                70,

            "mode":
                145,

            "result":
                260

        }


        for col in log_columns:

            self.log_tree.heading(

                col,

                text=headings[
                    col
                ]

            )


            self.log_tree.column(

                col,

                width=widths[
                    col
                ]

            )


        self.log_tree.pack(

            side="left",

            fill="both",

            expand=True

        )


        scrollbar = ttk.Scrollbar(

            log_frame,

            orient="vertical",

            command=self.log_tree.yview

        )


        scrollbar.pack(

            side="right",

            fill="y"

        )


        self.log_tree.configure(

            yscrollcommand=
                scrollbar.set

        )


        # ====================================================
        # Bottom
        # ====================================================

        self.operation_var = tk.StringVar(
            value="就绪"
        )


        ttk.Label(

            outer,

            textvariable=self.operation_var,

            relief="sunken",

            anchor="w"

        ).pack(

            fill="x",

            pady=(
                6,
                0
            )

        )


    # ========================================================
    # Right scroll
    # ========================================================

    def _pointer_inside_right_panel(
        self
    ):

        try:

            x = self.root.winfo_pointerx()

            y = self.root.winfo_pointery()


            left = self.right_container.winfo_rootx()

            top = self.right_container.winfo_rooty()


            return (

                left
                <=
                x
                <
                left
                +
                self.right_container.winfo_width()

                and

                top
                <=
                y
                <
                top
                +
                self.right_container.winfo_height()

            )


        except Exception:

            return False


    def _right_mousewheel(

        self,

        event

    ):

        if not self._pointer_inside_right_panel():

            return


        if event.delta == 0:

            return


        steps = (

            int(
                -event.delta
                /
                120
            )

            if abs(
                event.delta
            )
            >=
            120

            else

            (
                -1
                if event.delta > 0
                else
                1
            )

        )


        if steps == 0:

            steps = (
                -1
                if event.delta > 0
                else
                1
            )


        self.right_canvas.yview_scroll(

            steps,

            "units"

        )


        return "break"


    def _right_linux_scroll_up(
        self,
        _event
    ):

        if self._pointer_inside_right_panel():

            self.right_canvas.yview_scroll(
                -1,
                "units"
            )


            return "break"


    def _right_linux_scroll_down(
        self,
        _event
    ):

        if self._pointer_inside_right_panel():

            self.right_canvas.yview_scroll(
                1,
                "units"
            )


            return "break"


    # ========================================================
    # Serial ports
    # ========================================================

    def _refresh_ports(
        self
    ):

        ports = [

            item.device

            for item
            in list_ports.comports()

        ]


        self.port_combo[
            "values"
        ] = ports


        preferred = self.config.get(
            "last_serial_port",
            ""
        )


        if (
            preferred
            in
            ports
        ):

            self.port_var.set(
                preferred
            )


        elif ports:

            self.port_var.set(
                ports[0]
            )


    # ========================================================
    # Connection
    # ========================================================

    def _toggle_connection(
        self
    ):

        if self.ser is None:

            self._connect()

        else:

            self._disconnect()


    def _connect(
        self
    ):

        port = self.port_var.get().strip()


        if not port:

            messagebox.showwarning(

                "串口",

                "请选择串口。"

            )

            return


        try:

            self.ser = serial.Serial(

                port=port,

                baudrate=115200,

                bytesize=serial.EIGHTBITS,

                parity=serial.PARITY_NONE,

                stopbits=serial.STOPBITS_ONE,

                timeout=5.0,

                write_timeout=5.0

            )


            self.ser.reset_input_buffer()

            self.ser.reset_output_buffer()


            self.client = MultiUserFPGAClient(
                self.ser
            )


            self.config.set(
                "last_serial_port",
                port
            )


            self.connection_var.set(

                f"已连接 {port} @115200"

            )


            self.connect_button.configure(
                text="断开"
            )


            if self.auto_restore_var.get():

                self._restore_fpga_runtime(

                    automatic=True,

                    reason="串口连接"

                )


            else:

                self._refresh_fpga_users()


        except Exception as exc:

            try:

                if self.ser is not None:

                    self.ser.close()

            except Exception:

                pass


            self.ser = None

            self.client = None


            messagebox.showerror(

                "连接失败",

                str(
                    exc
                )

            )


    def _disconnect(
        self
    ):

        if self.operation_busy:

            messagebox.showwarning(

                "正在执行",

                "当前 FPGA 操作尚未完成。"

            )

            return


        if self.ser is not None:

            try:

                self.ser.close()

            except Exception:

                pass


        self.ser = None

        self.client = None

        self.last_fpga_status = None


        self.runtime_users = {

            user_id:
                None

            for user_id
            in range(
                MAX_USERS
            )

        }


        self.connection_var.set(
            "未连接"
        )


        self.connect_button.configure(
            text="连接"
        )


        self.status_door_var.set(
            "Door: --"
        )


        self.status_lockout_var.set(
            "Lockout: --"
        )


        self.status_mode_var.set(
            "Mode: --"
        )


        self._refresh_user_table()


    def _serial_connected(
        self
    ):

        return (

            self.ser is not None

            and

            self.client is not None

            and

            self.ser.is_open

        )


    def _require_connection(
        self
    ):

        if not self._serial_connected():

            messagebox.showwarning(

                "FPGA",

                "请先连接 FPGA 串口。"

            )

            return False


        return True


    # ========================================================
    # Async
    # ========================================================

    def _run_async(

        self,

        label,

        worker,

        success=None

    ):

        if not self._require_connection():

            return


        if self.operation_busy:

            messagebox.showwarning(

                "正在执行",

                "请等待当前 FPGA 操作完成。"

            )

            return


        self.operation_busy = True


        self.operation_var.set(
            label
        )


        def target():

            try:

                with self.serial_lock:

                    result = worker()


                self.root.after(

                    0,

                    lambda result=result:
                        self._async_done(

                            result,

                            None,

                            success

                        )

                )


            except Exception as exc:

                self.root.after(

                    0,

                    lambda error=exc:
                        self._async_done(

                            None,

                            error,

                            success

                        )

                )


        threading.Thread(

            target=target,

            daemon=True

        ).start()


    def _async_done(

        self,

        result,

        error,

        success

    ):

        self.operation_busy = False


        if error is not None:

            self.operation_var.set(
                "操作失败"
            )


            messagebox.showerror(

                "FPGA 操作失败",

                str(
                    error
                )

            )

            return


        self.operation_var.set(
            "就绪"
        )


        if success:

            success(
                result
            )


    # ========================================================
    # Camera
    # ========================================================

    def _toggle_camera(
        self
    ):

        if self.camera_running:

            self._stop_camera()

        else:

            self._start_camera()


    def _start_camera(
        self
    ):

        index = int(
            self.camera_index_var.get()
        )


        self.config.set(
            "camera_index",
            index
        )


        camera = cv2.VideoCapture(
            index
        )


        if not camera.isOpened():

            camera.release()


            messagebox.showerror(

                "摄像头",

                f"无法打开摄像头 {index}"

            )

            return


        self.camera = camera

        self.camera_running = True


        self.camera_button.configure(
            text="停止摄像头"
        )


        self._reset_auto_state()


        self._camera_tick()


    def _stop_camera(
        self
    ):

        self.camera_running = False


        if hasattr(
            self,
            "camera_button"
        ):

            self.camera_button.configure(
                text="启动摄像头"
            )


        if self.camera is not None:

            self.camera.release()

            self.camera = None


        self.live_face_pixels = None


    @staticmethod
    def _square_face_crop(

        frame,

        x,
        y,
        w,
        h

    ):

        frame_h, frame_w = frame.shape[
            :2
        ]


        cx = x + w // 2

        cy = y + h // 2


        side = int(

            max(
                w,
                h
            )
            *
            1.35

        )


        x1 = max(
            0,
            cx - side // 2
        )


        y1 = max(
            0,
            cy - side // 2
        )


        x2 = min(
            frame_w,
            x1 + side
        )


        y2 = min(
            frame_h,
            y1 + side
        )


        x1 = max(
            0,
            x2 - side
        )


        y1 = max(
            0,
            y2 - side
        )


        return frame[
            y1:y2,
            x1:x2
        ]


    def _camera_tick(
        self
    ):

        if not self.camera_running:

            return


        ok, frame = self.camera.read()


        face_present = False


        if ok:

            gray = cv2.cvtColor(

                frame,

                cv2.COLOR_BGR2GRAY

            )


            faces = self.face_detector.detectMultiScale(

                gray,

                scaleFactor=1.1,

                minNeighbors=5,

                minSize=(
                    80,
                    80
                )

            )


            self.live_face_pixels = None


            if len(
                faces
            ) > 0:

                x, y, w, h = max(

                    faces,

                    key=lambda item:
                        item[2]
                        *
                        item[3]

                )


                cv2.rectangle(

                    frame,

                    (
                        x,
                        y
                    ),

                    (
                        x + w,
                        y + h
                    ),

                    (
                        0,
                        255,
                        0
                    ),

                    2

                )


                crop = self._square_face_crop(

                    frame,

                    x,
                    y,
                    w,
                    h

                )


                if crop.size > 0:

                    pil_face = Image.fromarray(

                        cv2.cvtColor(

                            crop,

                            cv2.COLOR_BGR2RGB

                        )

                    ).convert(

                        "L"

                    ).resize(

                        (
                            64,
                            64
                        ),

                        Image.Resampling.LANCZOS

                    )


                    self.live_face_pixels = (
                        pil_face.tobytes()
                    )


                    face_present = True


            self.face_state_var.set(

                "检测到人脸"

                if face_present

                else

                "未检测到人脸"

            )


            self._handle_auto_face_presence(
                face_present
            )


            display = Image.fromarray(

                cv2.cvtColor(

                    frame,

                    cv2.COLOR_BGR2RGB

                )

            )


            display.thumbnail(

                (
                    700,
                    460
                ),

                Image.Resampling.LANCZOS

            )


            self.camera_photo = ImageTk.PhotoImage(
                display
            )


            self.camera_label.configure(
                image=self.camera_photo
            )


        self.root.after(

            30,

            self._camera_tick

        )


    # ========================================================
    # Capture
    # ========================================================

    def _set_captured_face_pixels(

        self,

        pixels

    ):

        self.captured_face_pixels = bytes(
            pixels
        )


        self.captured_face_pil = Image.frombytes(

            "L",

            (
                64,
                64
            ),

            self.captured_face_pixels

        )


        preview = self.captured_face_pil.resize(

            (
                192,
                192
            ),

            Image.Resampling.NEAREST

        )


        self.face_photo = ImageTk.PhotoImage(
            preview
        )


        self.face_preview_label.configure(
            image=self.face_photo
        )


    def _capture_face(
        self
    ):

        if self.live_face_pixels is None:

            messagebox.showwarning(

                "采集",

                "当前没有检测到人脸。"

            )

            return


        self._set_captured_face_pixels(
            self.live_face_pixels
        )


        self.result_var.set(
            "已采集人脸"
        )


    # ========================================================
    # Dynamic users
    # ========================================================

    def _refresh_user_table(
        self
    ):

        old_selection = self.user_tree.selection()


        for item in self.user_tree.get_children():

            self.user_tree.delete(
                item
            )


        for user in self.db.list_users():

            user_id = user[
                "user_id"
            ]


            runtime = self.runtime_users.get(
                user_id
            )


            if runtime is None:

                fpga_permission = "--"

                template = "--"


            else:

                fpga_permission = (

                    "ON"

                    if runtime[
                        "enabled"
                    ]

                    else

                    "OFF"

                )


                template = (

                    "VALID"

                    if runtime[
                        "template_valid"
                    ]

                    else

                    "EMPTY"

                )


            self.user_tree.insert(

                "",

                "end",

                iid=str(
                    user_id
                ),

                values=(

                    user_id,

                    user[
                        "name"
                    ],

                    (
                        "ON"

                        if user[
                            "enabled"
                        ]

                        else

                        "OFF"

                    ),

                    fpga_permission,

                    template

                )

            )


        self.user_capacity_var.set(

            f"已添加用户：{self.db.used_count()}/{MAX_USERS}"

        )


        if old_selection:

            item = old_selection[0]


            if self.user_tree.exists(
                item
            ):

                self.user_tree.selection_set(
                    item
                )


    def _selected_user_id(
        self
    ):

        selection = self.user_tree.selection()


        if not selection:

            messagebox.showwarning(

                "用户",

                "请先在用户表中选择一个用户。"

            )

            return None


        return int(
            selection[0]
        )


    # ========================================================
    # Add user
    # ========================================================

    def _add_user(
        self
    ):

        free_id = self.db.find_free_user_id()


        if free_id is None:

            messagebox.showwarning(

                "添加用户",

                "FPGA 的 8 个用户槽位已经全部使用。"

            )

            return


        name = simpledialog.askstring(

            "添加用户",

            f"将自动分配 USER{free_id}\n\n请输入用户姓名：",

            parent=self.root

        )


        if name is None:

            return


        try:

            user_id = self.db.add_user(
                name
            )


            self._refresh_user_table()


            self.user_tree.selection_set(
                str(
                    user_id
                )
            )


            self.user_tree.focus(
                str(
                    user_id
                )
            )


            messagebox.showinfo(

                "添加用户",

                f"用户已添加。\n\n"
                f"FPGA槽位：USER{user_id}\n"
                f"姓名：{self.db.get_name(user_id)}\n\n"
                f"下一步请采集人脸并点击“将当前人脸注册到选中用户”。"

            )


        except Exception as exc:

            messagebox.showerror(

                "添加用户",

                str(
                    exc
                )

            )


    # ========================================================
    # Delete user
    #
    # For consistency the FPGA template is cleared FIRST.
    # Only after ACK is received is the PC database record
    # removed.
    # ========================================================

    def _delete_user(
        self
    ):

        user_id = self._selected_user_id()


        if user_id is None:

            return


        name = self.db.get_name(
            user_id
        )


        if not messagebox.askyesno(

            "删除用户",

            f"确认删除：\n\n"
            f"USER{user_id}\n"
            f"{name}\n\n"
            f"FPGA模板和访问权限也会同时清除。"

        ):

            return


        if not self._serial_connected():

            messagebox.showwarning(

                "删除用户",

                "为了防止 FPGA 留下孤立模板，"
                "删除用户时必须先连接 FPGA。"

            )

            return


        def worker():

            self.client.clear_user(
                user_id
            )


            return self.client.get_all_user_status()


        def success(
            runtime
        ):

            self.db.remove_user(
                user_id
            )


            self.runtime_users = runtime


            self._refresh_user_table()


            messagebox.showinfo(

                "删除用户",

                f"USER{user_id} 已删除，"
                "FPGA模板和权限已清除。"

            )


        self._run_async(

            f"删除 USER{user_id}...",

            worker,

            success

        )


    # ========================================================
    # Rename
    # ========================================================

    def _rename_user(
        self
    ):

        user_id = self._selected_user_id()


        if user_id is None:

            return


        name = simpledialog.askstring(

            "修改用户名",

            f"USER{user_id} 名称：",

            initialvalue=self.db.get_name(
                user_id
            ),

            parent=self.root

        )


        if name is None:

            return


        self.db.set_name(

            user_id,

            name

        )


        self._refresh_user_table()


    # ========================================================
    # Permission
    # ========================================================

    def _toggle_pc_permission(
        self
    ):

        user_id = self._selected_user_id()


        if user_id is None:

            return


        self.db.set_enabled(

            user_id,

            not self.db.is_enabled(
                user_id
            )

        )


        self._refresh_user_table()


    def _sync_permissions(
        self
    ):

        def worker():

            # Existing PC users.

            for user_id in range(
                MAX_USERS
            ):

                if self.db.user_exists(
                    user_id
                ):

                    enabled = self.db.is_enabled(
                        user_id
                    )


                else:

                    enabled = False


                self.client.set_permission(

                    user_id,

                    enabled

                )


            return self.client.get_all_user_status()


        def success(
            runtime
        ):

            self.runtime_users = runtime


            self._refresh_user_table()


            messagebox.showinfo(

                "权限同步",

                "全部用户权限已同步到 FPGA。"

            )


        self._run_async(

            "同步全部用户权限...",

            worker,

            success

        )


    # ========================================================
    # FPGA user state
    # ========================================================

    def _refresh_fpga_users(
        self
    ):

        def worker():

            return {

                "status":
                    self.client.get_status(),

                "users":
                    self.client.get_all_user_status()

            }


        def success(
            result
        ):

            self.runtime_users = result[
                "users"
            ]


            self._update_status_display(
                result[
                    "status"
                ]
            )


            self._refresh_user_table()


        self._run_async(

            "查询 FPGA 8 用户状态...",

            worker,

            success

        )


    # ========================================================
    # Status
    # ========================================================

    def _update_status_display(

        self,

        status

    ):

        self.last_fpga_status = dict(
            status
        )


        self.status_door_var.set(

            "Door: OPEN"

            if status[
                "lock_open"
            ]

            else

            "Door: CLOSED"

        )


        self.status_lockout_var.set(

            "Lockout: YES"

            if status[
                "lockout"
            ]

            else

            "Lockout: NO"

        )


        self.status_mode_var.set(

            "Mode: "
            +
            AUTH_MODE_NAMES.get(

                status[
                    "auth_mode"
                ],

                "UNKNOWN"

            )

        )


        # Do NOT overwrite auth_mode_var here.


    def _manual_refresh_status(
        self
    ):

        self._run_async(

            "读取系统状态...",

            self.client.get_status,

            self._update_status_display

        )


    # ========================================================
    # Background polling + FPGA reset detection
    # ========================================================

    def _auto_status_tick(
        self
    ):

        self.status_poll_count += 1


        probe_users = (
            self.status_poll_count
            %
            5
            ==
            0
        )


        if (

            self._serial_connected()

            and

            not self.operation_busy

        ):

            def worker():

                if not self.serial_lock.acquire(
                    blocking=False
                ):

                    return


                try:

                    result = {

                        "status":
                            self.client.get_status(),

                        "users":
                            None

                    }


                    if probe_users:

                        result[
                            "users"
                        ] = (
                            self.client.get_all_user_status()
                        )


                    self.root.after(

                        0,

                        lambda result=result:
                            self._handle_background_probe(
                                result
                            )

                    )


                except Exception:

                    pass


                finally:

                    self.serial_lock.release()


            threading.Thread(

                target=worker,

                daemon=True

            ).start()


        self.root.after(

            800,

            self._auto_status_tick

        )


    def _handle_background_probe(

        self,

        result

    ):

        self._update_status_display(
            result[
                "status"
            ]
        )


        users = result[
            "users"
        ]


        if users is None:

            return


        previous_mask = 0

        current_mask = 0


        for user_id in range(
            MAX_USERS
        ):

            old = self.runtime_users.get(
                user_id
            )


            if (
                old is not None
                and
                old[
                    "template_valid"
                ]
            ):

                previous_mask |= (
                    1
                    <<
                    user_id
                )


            if users[
                user_id
            ][
                "template_valid"
            ]:

                current_mask |= (
                    1
                    <<
                    user_id
                )


        self.runtime_users = users


        self._refresh_user_table()


        if (

            previous_mask
            !=
            0

            and

            current_mask
            ==
            0

            and

            self.auto_restore_var.get()

            and

            not self.reset_restore_pending

        ):

            self.reset_restore_pending = True


            self.restore_state_var.set(

                "检测到 FPGA 模板清空，准备恢复..."

            )


            self.root.after(

                100,

                lambda:
                    self._restore_fpga_runtime(

                        automatic=True,

                        reason="检测到FPGA复位"

                    )

            )


    # ========================================================
    # Mode
    # ========================================================

    def _set_auth_mode(
        self
    ):

        mode_name = self.auth_mode_var.get()


        mode = MODE_NAME_TO_VALUE[
            mode_name
        ]


        def worker():

            self.client.set_auth_mode(
                mode
            )


            status = self.client.get_status()


            if status[
                "auth_mode"
            ] != mode:

                raise RuntimeError(
                    "认证模式写入后校验失败"
                )


            return status


        def success(
            status
        ):

            self.config.set(
                "auth_mode",
                mode
            )


            self._update_status_display(
                status
            )


            self._reset_auto_state()


            messagebox.showinfo(

                "认证模式",

                f"已切换为 {mode_name}"

            )


        self._run_async(

            f"切换认证模式 {mode_name}...",

            worker,

            success

        )


    # ========================================================
    # Threshold
    # ========================================================

    def _parse_threshold(
        self
    ):

        threshold = int(
            self.threshold_var.get().strip()
        )


        if not (
            0
            <=
            threshold
            <=
            65535
        ):

            raise ValueError(
                "阈值必须是 0..65535"
            )


        return threshold


    def _set_threshold(
        self
    ):

        try:

            threshold = self._parse_threshold()


        except Exception as exc:

            messagebox.showerror(

                "阈值",

                str(
                    exc
                )

            )

            return


        def success(
            _result
        ):

            self.config.set(

                "match_threshold",

                threshold

            )


            messagebox.showinfo(

                "阈值",

                f"已保存阈值 {threshold}"

            )


        self._run_async(

            f"写入阈值 {threshold}...",

            lambda:
                self.client.set_threshold(
                    threshold
                ),

            success

        )


    # ========================================================
    # Restore option
    # ========================================================

    def _on_auto_restore_toggle(
        self
    ):

        self.config.set(

            "auto_restore_on_connect",

            bool(
                self.auto_restore_var.get()
            )

        )


    def _manual_restore_fpga(
        self
    ):

        self._restore_fpga_runtime(

            automatic=False,

            reason="手动恢复"

        )


    # ========================================================
    # Template paths
    # ========================================================

    def _resolve_template_path(

        self,

        user_id

    ):

        text = str(

            self.db.get_user(
                user_id
            ).get(
                "template_image",
                ""
            )

        ).strip()


        if not text:

            return None


        path = Path(
            text
        )


        if not path.is_absolute():

            path = (
                self.db.path.parent
                /
                path
            )


        return path


    @staticmethod
    def _load_template_pixels(
        path
    ):

        with Image.open(
            path
        ) as image:

            return image.convert(

                "L"

            ).resize(

                (
                    64,
                    64
                ),

                Image.Resampling.LANCZOS

            ).tobytes()


    # ========================================================
    # Full FPGA restore
    #
    # PC database becomes authoritative:
    #
    # PC slot exists:
    #   restore template if needed
    #
    # PC slot does NOT exist:
    #   clear any orphan FPGA template
    #
    # Then restore permissions / threshold / mode.
    # ========================================================

    def _restore_fpga_runtime(

        self,

        automatic=False,

        reason="恢复"

    ):

        if not self._serial_connected():

            if not automatic:

                messagebox.showwarning(

                    "恢复",

                    "请先连接 FPGA。"

                )

            return


        if self.operation_busy:

            return


        def worker():

            report = {

                "restored":
                    [],

                "missing":
                    [],

                "cleared":
                    []

            }


            runtime = self.client.get_all_user_status()


            # =================================================
            # Threshold
            # =================================================

            threshold = self.config.get(
                "match_threshold"
            )


            if threshold is not None:

                self.client.set_threshold(
                    threshold
                )


            # =================================================
            # Templates
            # =================================================

            for user_id in range(
                MAX_USERS
            ):

                pc_exists = self.db.user_exists(
                    user_id
                )


                fpga_valid = runtime[
                    user_id
                ][
                    "template_valid"
                ]


                # =============================================
                # No PC user = clear orphan hardware slot
                # =============================================

                if not pc_exists:

                    if (
                        fpga_valid
                        or
                        runtime[
                            user_id
                        ][
                            "enabled"
                        ]
                    ):

                        self.client.clear_user(
                            user_id
                        )


                        report[
                            "cleared"
                        ].append(
                            user_id
                        )


                    continue


                # =============================================
                # Existing hardware template stays unchanged
                # =============================================

                if fpga_valid:

                    continue


                path = self._resolve_template_path(
                    user_id
                )


                if (
                    path is None
                    or
                    not path.exists()
                ):

                    report[
                        "missing"
                    ].append(
                        user_id
                    )


                    continue


                pixels = self._load_template_pixels(
                    path
                )


                self._run_verified_pipeline(

                    pixels,

                    self._next_frame_id()

                )


                self.client.enroll_current(
                    user_id
                )


                report[
                    "restored"
                ].append(
                    user_id
                )


            # =================================================
            # Permissions
            #
            # Do this after enrollment because enrollment
            # automatically enables the slot.
            # =================================================

            for user_id in range(
                MAX_USERS
            ):

                enabled = (

                    self.db.is_enabled(
                        user_id
                    )

                    if self.db.user_exists(
                        user_id
                    )

                    else

                    False

                )


                self.client.set_permission(

                    user_id,

                    enabled

                )


            # =================================================
            # Mode last
            # =================================================

            self.client.set_auth_mode(

                self.config.get(
                    "auth_mode",
                    0
                )

            )


            report[
                "status"
            ] = self.client.get_status()


            report[
                "users"
            ] = self.client.get_all_user_status()


            return report


        def success(
            report
        ):

            self.reset_restore_pending = False


            self.runtime_users = report[
                "users"
            ]


            self._update_status_display(
                report[
                    "status"
                ]
            )


            self._refresh_user_table()


            parts = []


            if report[
                "restored"
            ]:

                parts.append(

                    "恢复模板："
                    +
                    ",".join(

                        f"USER{x}"

                        for x in report[
                            "restored"
                        ]

                    )

                )


            if report[
                "cleared"
            ]:

                parts.append(

                    "清理孤立槽位："
                    +
                    ",".join(

                        f"USER{x}"

                        for x in report[
                            "cleared"
                        ]

                    )

                )


            if report[
                "missing"
            ]:

                parts.append(

                    "未注册模板："
                    +
                    ",".join(

                        f"USER{x}"

                        for x in report[
                            "missing"
                        ]

                    )

                )


            if not parts:

                parts.append(
                    "FPGA运行状态已同步"
                )


            self.restore_state_var.set(

                " | ".join(
                    parts
                )

            )


            if (
                not automatic
                and
                report[
                    "missing"
                ]
            ):

                messagebox.showwarning(

                    "恢复完成",

                    "以下用户尚未保存人脸模板：\n\n"
                    +
                    "\n".join(

                        f"USER{x} "
                        f"({self.db.get_name(x)})"

                        for x in report[
                            "missing"
                        ]

                    )

                )


            elif not automatic:

                messagebox.showinfo(

                    "恢复完成",

                    "FPGA运行状态恢复完成。"

                )


        self._run_async(

            f"{reason}：恢复 FPGA...",

            worker,

            success

        )


    # ========================================================
    # Remote open
    # ========================================================

    def _remote_open(
        self
    ):

        def worker():

            self.client.remote_open()


            time.sleep(
                0.05
            )


            return self.client.get_status()


        self._run_async(

            "远程开门...",

            worker,

            self._update_status_display

        )


    # ========================================================
    # Face helpers
    # ========================================================

    def _next_frame_id(
        self
    ):

        value = self.frame_id


        self.frame_id += 1


        if self.frame_id > 255:

            self.frame_id = 1


        return value


    @staticmethod
    def _save_face_pixels(

        pixels,

        folder,

        prefix

    ):

        folder = Path(
            folder
        )


        folder.mkdir(

            parents=True,

            exist_ok=True

        )


        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )


        path = folder / (
            f"{prefix}_{stamp}.png"
        )


        Image.frombytes(

            "L",

            (
                64,
                64
            ),

            pixels

        ).save(
            path
        )


        return path


    def _run_verified_pipeline(

        self,

        pixels,

        frame_id

    ):

        hidden = io.StringIO()


        with contextlib.redirect_stdout(
            hidden
        ):

            send_image.send_image(

                self.ser,

                pixels,

                frame_id

            )


    # ========================================================
    # Enrollment
    # ========================================================

    def _enroll_selected_user(
        self
    ):

        user_id = self._selected_user_id()


        if user_id is None:

            return


        if self.captured_face_pixels is None:

            messagebox.showwarning(

                "注册",

                "请先采集当前人脸。"

            )

            return


        pixels = bytes(
            self.captured_face_pixels
        )


        image_path = self._save_face_pixels(

            pixels,

            "captured_templates",

            f"user{user_id}"

        )


        frame_id = self._next_frame_id()


        def worker():

            self._run_verified_pipeline(

                pixels,

                frame_id

            )


            self.client.enroll_current(
                user_id
            )


            self.client.set_permission(

                user_id,

                self.db.is_enabled(
                    user_id
                )

            )


            return self.client.get_all_user_status()


        def success(
            runtime
        ):

            self.db.set_template_image(

                user_id,

                str(
                    image_path
                )

            )


            self.runtime_users = runtime


            self._refresh_user_table()


            self.result_var.set(

                f"USER{user_id} / "
                f"{self.db.get_name(user_id)}\n"
                f"注册成功，Template=VALID"

            )


        self._run_async(

            f"注册 USER{user_id}...",

            worker,

            success

        )


    # ========================================================
    # Recognition
    # ========================================================

    def _recognize_captured_face(
        self
    ):

        if self.captured_face_pixels is None:

            messagebox.showwarning(

                "识别",

                "请先采集当前人脸。"

            )

            return


        self._start_recognition(

            bytes(
                self.captured_face_pixels
            ),

            source="manual"

        )


    def _start_recognition(

        self,

        pixels,

        source

    ):

        frame_id = self._next_frame_id()


        image_path = self._save_face_pixels(

            pixels,

            "captures",

            (
                "auto_match"

                if source == "auto"

                else

                "match"
            )

        )


        def worker():

            self._run_verified_pipeline(

                pixels,

                frame_id

            )


            match = self.client.match_current()


            time.sleep(
                0.10
            )


            status = self.client.get_status()


            if match[
                "recognized"
            ]:

                user_id = match[
                    "user_id"
                ]


                user_name = self.db.get_display_name(
                    user_id
                )


            else:

                user_id = ""

                user_name = "UNKNOWN"


            if not match[
                "recognized"
            ]:

                result_text = "UNKNOWN"


            elif not match[
                "authorized"
            ]:

                result_text = (
                    "RECOGNIZED_BUT_PERMISSION_DENIED"
                )


            elif status[
                "lockout"
            ]:

                result_text = (
                    "AUTHORIZED_FACE_BUT_LOCKOUT"
                )


            elif status[
                "lock_open"
            ]:

                result_text = "DOOR_OPEN"


            elif status[
                "auth_mode"
            ] == 2:

                result_text = (
                    "FACE_OK_WAITING_SECOND_FACTOR"
                )


            elif status[
                "auth_mode"
            ] == 0:

                result_text = (
                    "FACE_OK_IGNORED_IN_PASSWORD_MODE"
                )


            else:

                result_text = "FACE_AUTHORIZED"


            self.logger.log({

                "frame_id":
                    match[
                        "frame_id"
                    ],

                "user_id":
                    user_id,

                "user_name":
                    user_name,

                "recognized":
                    int(
                        match[
                            "recognized"
                        ]
                    ),

                "authorized":
                    int(
                        match[
                            "authorized"
                        ]
                    ),

                # Multi-user protocol no longer transmits
                # individual D0/D1.

                "distance_user0":
                    "",

                "distance_user1":
                    "",

                "best_distance":
                    match[
                        "best_distance"
                    ],

                "threshold":
                    match[
                        "threshold"
                    ],

                "template_valid_bits":
                    f"{match['template_valid_mask']:08b}",

                "user_enabled_bits":
                    f"{match['user_enabled_mask']:08b}",

                "auth_mode":
                    AUTH_MODE_NAMES.get(
                        status[
                            "auth_mode"
                        ],
                        "UNKNOWN"
                    ),

                "door_open":
                    int(
                        status[
                            "lock_open"
                        ]
                    ),

                "lockout":
                    int(
                        status[
                            "lockout"
                        ]
                    ),

                "result":
                    result_text,

                "image":
                    str(
                        image_path
                    )

            })


            return {

                "match":
                    match,

                "status":
                    status,

                "name":
                    user_name,

                "result":
                    result_text,

                "source":
                    source

            }


        def success(
            data
        ):

            match = data[
                "match"
            ]


            if match[
                "recognized"
            ]:

                identity = (

                    f"USER{match['user_id']} / "
                    f"{data['name']}"

                )


            else:

                identity = "UNKNOWN"


            self.result_var.set(

                f"[{data['source'].upper()}] "
                f"{identity}\n"

                f"recognized="
                f"{int(match['recognized'])}  "

                f"authorized="
                f"{int(match['authorized'])}\n"

                f"Best="
                f"{match['best_distance']}  "

                f"T="
                f"{match['threshold']}\n"

                f"Templates="
                f"{match['template_valid_mask']:08b}\n"

                f"Result="
                f"{data['result']}"

            )


            self._update_status_display(
                data[
                    "status"
                ]
            )


            self._refresh_log_table()


            if data[
                "source"
            ] == "auto":

                self.auto_state_var.set(

                    f"{data['result']}；"
                    "等待人脸离开后重新布防"

                )


        self._run_async(

            "执行多用户 FPGA 人脸识别...",

            worker,

            success

        )


    # ========================================================
    # Automatic recognition
    # ========================================================

    def _reset_auto_state(
        self
    ):

        self.auto_face_stable_count = 0

        self.auto_absent_count = 0

        self.auto_armed = True


    def _on_auto_toggle(
        self
    ):

        self.config.set(

            "auto_recognition",

            bool(
                self.auto_enabled_var.get()
            )

        )


        self._reset_auto_state()


    def _get_auto_stable_frames(
        self
    ):

        try:

            return max(

                3,

                min(

                    60,

                    int(
                        self.auto_stable_frames_var.get()
                    )

                )

            )


        except Exception:

            return 8


    def _get_auto_cooldown(
        self
    ):

        try:

            return max(

                1.0,

                min(

                    60.0,

                    float(
                        self.auto_cooldown_var.get()
                    )

                )

            )


        except Exception:

            return 5.0


    def _handle_auto_face_presence(

        self,

        face_present

    ):

        if not self.auto_enabled_var.get():

            return


        if not self._serial_connected():

            self.auto_state_var.set(
                "等待 FPGA"
            )

            return


        if self.last_fpga_status is None:

            return


        if self.last_fpga_status[
            "auth_mode"
        ] == 0:

            self.auto_state_var.set(
                "PASSWORD_ONLY：自动人脸识别暂停"
            )

            return


        if not face_present:

            self.auto_face_stable_count = 0


            if not self.auto_armed:

                self.auto_absent_count += 1


                if (

                    self.auto_absent_count
                    >=
                    self.auto_rearm_absent_frames

                ):

                    self.auto_armed = True

                    self.auto_absent_count = 0


                    self.auto_state_var.set(
                        "已重新布防"
                    )


            return


        self.auto_absent_count = 0


        if not self.auto_armed:

            return


        if self.operation_busy:

            return


        required = self._get_auto_stable_frames()


        self.auto_face_stable_count += 1


        self.auto_state_var.set(

            f"稳定人脸 "
            f"{self.auto_face_stable_count}/"
            f"{required}"

        )


        if self.auto_face_stable_count < required:

            return


        cooldown = self._get_auto_cooldown()


        if (

            time.monotonic()
            -
            self.auto_last_trigger_time

            <
            cooldown

        ):

            return


        if self.live_face_pixels is None:

            return


        pixels = bytes(
            self.live_face_pixels
        )


        self.auto_armed = False

        self.auto_face_stable_count = 0

        self.auto_last_trigger_time = (
            time.monotonic()
        )


        self._set_captured_face_pixels(
            pixels
        )


        self._start_recognition(

            pixels,

            source="auto"

        )


    # ========================================================
    # Access log
    # ========================================================

    def _refresh_log_table(
        self
    ):

        for item in self.log_tree.get_children():

            self.log_tree.delete(
                item
            )


        path = Path(
            self.logger.path
        )


        if not path.exists():

            return


        try:

            with open(

                path,

                "r",

                newline="",

                encoding="utf-8-sig"

            ) as file:

                rows = list(
                    csv.DictReader(
                        file
                    )
                )


        except Exception:

            return


        for row in rows[
            -100:
        ][
            ::-1
        ]:

            self.log_tree.insert(

                "",

                "end",

                values=(

                    row.get(
                        "timestamp",
                        ""
                    ),

                    row.get(
                        "user_name",
                        ""
                    ),

                    row.get(
                        "recognized",
                        ""
                    ),

                    row.get(
                        "authorized",
                        ""
                    ),

                    row.get(
                        "best_distance",
                        ""
                    ),

                    row.get(
                        "auth_mode",
                        ""
                    ),

                    row.get(
                        "result",
                        ""
                    )

                )

            )


    # ========================================================
    # Close
    # ========================================================

    def _on_close(
        self
    ):

        self.config.set(

            "auto_stable_frames",

            self._get_auto_stable_frames()

        )


        self.config.set(

            "auto_cooldown_seconds",

            self._get_auto_cooldown()

        )


        self._stop_camera()


        try:

            if self.ser is not None:

                self.ser.close()

        except Exception:

            pass


        self.root.destroy()


# ============================================================
# Main
# ============================================================

def main():

    root = tk.Tk()


    SmartAccessGUI(
        root
    )


    root.mainloop()


if __name__ == "__main__":

    main()
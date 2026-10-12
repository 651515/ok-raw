"""应用 ok-raw 对 ok-script 框架的必要改动。

这些改动在 .venv/Lib/site-packages/ok/ 下, 因 .venv 在 gitignore 中不纳入版本控制。
每次重新 pip install ok-script 后需跑本脚本重新应用补丁。

用法: python apply_framework_patch.py
"""
import os
import sys

VENV_OK = os.path.join(os.path.dirname(__file__), '.venv', 'Lib', 'site-packages', 'ok')


def patch_device_manager():
    dm = os.path.join(VENV_OK, 'device', 'DeviceManager.py')
    with open(dm, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. __init__: 支持 exe dict 映射 + _exe_class_map 存储
    old1 = """        if self.windows_capture_config is not None:
            if isinstance(self.windows_capture_config.get('exe'), str):
                self.windows_capture_config['exe'] = [self.windows_capture_config.get('exe')]"""
    new1 = """        if self.windows_capture_config is not None:
            exe_cfg = self.windows_capture_config.get('exe')
            if isinstance(exe_cfg, str):
                self.windows_capture_config['exe'] = [exe_cfg]
            elif isinstance(exe_cfg, dict):
                # 映射格式 {进程名: 可选的窗口类过滤(str/list/None)}
                self._exe_class_map = {k.lower(): v for k, v in exe_cfg.items()}
                self.windows_capture_config['exe'] = list(exe_cfg.keys())"""
    if old1 in content:
        content = content.replace(old1, new1, 1)
        print('[OK] DeviceManager __init__ exe dict 映射')
    elif '_exe_class_map' in content:
        print('[SKIP] DeviceManager __init__ 已打过补丁')
    else:
        print('[FAIL] DeviceManager __init__ 未找到锚点')
        return False

    # 2. __init__: 多设备枚举分支 (替换原 find_hwnd 截断调用)
    # 补丁目标: 在 "if self.windows_capture_config.get('multi_device'):" 处插入自枚举
    marker = """            if self.windows_capture_config.get('multi_device'):"""
    if 'enum_match' in content:
        print('[SKIP] DeviceManager multi_device 已打过补丁')
    elif marker in content:
        patch_block = '''            if self.windows_capture_config.get('multi_device'):
                # 原生多设备模式: 按 exe→hwnd_class 映射自枚举全部匹配窗口,
                # 每个窗口一个设备条目(不能用 find_hwnd, 它只返回面积最大/selected 的单窗口)
                from ok.util.window import _match_class_name, get_exe_by_hwnd, get_window_bounds
                import win32gui
                exe_map = getattr(self, '_exe_class_map', None)
                if exe_map is None:
                    exe_list = self.windows_capture_config.get('exe') or self.config.get('selected_exe')
                    if isinstance(exe_list, str):
                        exe_list = [exe_list]
                    exe_map = {e.lower(): None for e in (exe_list or [])}
                exclude_class = self.windows_capture_config.get('exclude_hwnd_class')
                pc_devices = {}

                def enum_match(hwnd, _):
                    try:
                        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowEnabled(hwnd) \\
                                or not win32gui.IsWindowVisible(hwnd):
                            return True
                        cname = win32gui.GetClassName(hwnd)
                        if exclude_class and _match_class_name(cname, exclude_class) >= 0:
                            return True
                        name, full_path, _ = get_exe_by_hwnd(hwnd)
                        if not name:
                            return True
                        allowed_class = exe_map.get(name.lower())
                        if allowed_class is None and name.lower() not in exe_map:
                            return True  # 进程不在白名单
                        if allowed_class and _match_class_name(cname, allowed_class) < 0:
                            return True  # 进程的窗口类不匹配
                        x, y, _, _, width, height, m_scaling = get_window_bounds(hwnd)
                        if width <= 10 or height <= 10:
                            return True
                        text = win32gui.GetWindowText(hwnd)
                        exe_name = os.path.basename(full_path) if full_path else name
                        imei = f"pc_{hwnd}"
                        pc_devices[imei] = {
                            "address": "", "imei": imei, "device": "windows",
                            "model": "", "nick": text or exe_name, "width": width,
                            "height": height, "hwnd": text or exe_name,
                            "capture": "windows", "connected": True,
                            "full_path": full_path or self.config.get('pc_full_path'),
                            "real_hwnd": hwnd, "exe": exe_name,
                            "resolution": f"{width}x{height}"
                        }
                    except Exception as e:
                        logger.error('multi_device enum window error', e)
                    return True

                win32gui.EnumWindows(enum_match, None)
                if not pc_devices:
                    # 枚举不到窗口时生成占位条目(connected=False), 保证 preferred 可取到、
                    # start_device 仍会走 execute 拉起启动器, 否则设备列表为空导致自启动失效
                    imei = self.config.get('preferred') or 'pc'
                    exe_list = self.windows_capture_config.get('exe') or self.config.get('selected_exe')
                    if isinstance(exe_list, str):
                        exe_list = [exe_list]
                    pc_devices[imei] = {
                        "address": "", "imei": imei, "device": "windows",
                        "model": "", "nick": (exe_list[0] if exe_list else "PC"),
                        "width": 0, "height": 0, "hwnd": "", "capture": "windows",
                        "connected": False,
                        "full_path": self.config.get('pc_full_path'),
                        "real_hwnd": 0, "exe": exe_list or [],
                        "resolution": ""
                    }
                self._replace_pc_devices(pc_devices)
                return self.config.get("preferred")

            if self.windows_capture_config.get('multi_device__done'):
                pass

'''  # 末尾加一个占位 if, 下面要删掉
        # 找到原 multi_device 块的完整范围替换
        idx = content.index(marker)
        # 找到下一个 "name, hwnd, full_path, x, y, width, height, hwnds = find_hwnd"
        next_fh = content.index('find_hwnd(self.windows_capture_config.get', idx)
        # 回退到上一个换行
        line_start = content.rindex('\n', 0, next_fh) + 1
        old_block = content[idx:line_start]
        # 还要删掉占位 if
        placeholder_if = '''            if self.windows_capture_config.get('multi_device__done'):
                pass

'''
        new_block = patch_block.rstrip() + '\n\n'
        content = content.replace(old_block, new_block + content[line_start:], 1)
        if placeholder_if in content:
            content = content.replace(placeholder_if, '', 1)
        print('[OK] DeviceManager multi_device 自枚举分支')
    else:
        print('[FAIL] DeviceManager 未找到 multi_device 锚点')
        return False

    # 3. __init__: 定时刷新线程
    old3 = """        else:
            self.hwnd_window = None

        logger.info('__init__ end')"""
    new3 = """        else:
            self.hwnd_window = None

        # 设备列表定时自动刷新(seconds, windows 配置段 device_refresh_interval), 0/缺省=关闭
        refresh_interval = self.windows_capture_config.get(
            'device_refresh_interval', 0) if self.windows_capture_config else 0
        if refresh_interval and refresh_interval > 0:
            def refresh_loop():
                while not self.exit_event.wait(refresh_interval):
                    try:
                        self.update_pc_device()
                        self.update_browser_device()
                        from ok.core.events import communicate
                        communicate.adb_devices.emit(True)
                    except Exception as e:
                        logger.error('device refresh loop error', e)

            threading.Thread(target=refresh_loop, daemon=True,
                             name='DeviceRefreshLoop').start()

        logger.info('__init__ end')"""
    if old3 in content:
        content = content.replace(old3, new3, 1)
        print('[OK] DeviceManager __init__ 定时刷新线程')
    elif 'DeviceRefreshLoop' in content:
        print('[SKIP] DeviceManager 定时刷新已打过补丁')
    else:
        print('[FAIL] DeviceManager __init__ 未找到 end 锚点')
        return False

    with open(dm, 'w', encoding='utf-8') as f:
        f.write(content)
    return True


def patch_ok_init():
    init_py = os.path.join(VENV_OK, '__init__.py')
    with open(init_py, 'r', encoding='utf-8') as f:
        content = f.read()

    old = """        logger.info('quit app')
        self.exit_event.set()
        if self._app:
            self._app.quit()
        if self._headless_app:
            self._headless_app.quit()"""
    new = """        logger.info('quit app')
        self.exit_event.set()
        if self._app:
            self._app.quit()
        if self._headless_app:
            self._headless_app.quit()
        # 兜底: Qt 退出后仍可能有非 daemon 线程(截图/Handler)残留导致进程不退、终端卡住,
        # 给 2 秒宽限正常清理(保存配置等), 之后强制结束进程
        def _force_exit():
            time.sleep(2)
            logger.info('force exit process')
            os._exit(0)

        threading.Thread(target=_force_exit, daemon=True, name='ForceExit').start()"""
    if old in content:
        content = content.replace(old, new, 1)
        print('[OK] __init__.py quit 兜底强制退出')
    elif 'ForceExit' in content:
        print('[SKIP] __init__.py quit 已打过补丁')
    else:
        print('[FAIL] __init__.py 未找到 quit 锚点')
        return False

    with open(init_py, 'w', encoding='utf-8') as f:
        f.write(content)
    return True


if __name__ == '__main__':
    if not os.path.isdir(VENV_OK):
        print(f'[FATAL] 找不到 ok 安装目录: {VENV_OK}')
        sys.exit(1)
    ok1 = patch_device_manager()
    ok2 = patch_ok_init()
    if ok1 and ok2:
        print('\n全部补丁应用成功。')
    else:
        print('\n部分补丁失败, 请手动检查。')
        sys.exit(1)

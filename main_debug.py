import os
import sys

# Windows 中文系统默认 GBK 编码, 项目特征名/配置含 UTF-8 中文;
# 未启用 UTF-8 模式时用 subprocess.call 重启(进程替换会导致 IDE 终端输出断开)
if sys.platform == 'win32' and sys.flags.utf8_mode == 0:
    import subprocess
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    sys.exit(subprocess.call([sys.executable, '-X', 'utf8'] + sys.argv, env=env))

# 开发模式下 pyappify 没有打包的 launcher exe, 设置测试模式让它 mock 更新请求, 避免 FileNotFoundError
os.environ.setdefault('PYAPPIFY_PYTHON_TEST', '1')

# 强制把工作目录切到脚本所在目录, 保证从任意 cwd 启动时 configs/logs/screenshots 都落在项目内
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import ok
from src.config import config

if __name__ == '__main__':
    config = config
    config['debug'] = True
    ok = ok.OK(config)
    ok.start()

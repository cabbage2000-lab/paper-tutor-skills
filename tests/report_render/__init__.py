"""共享报告渲染器单元测试包——导入时把 _shared 注入 sys.path，clone 即测、无需环境变量。"""
import pathlib
import sys

_SHARED = pathlib.Path(__file__).resolve().parents[2] / "skills" / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

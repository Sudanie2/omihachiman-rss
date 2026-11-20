import sys
from pathlib import Path

# scripts/ 内のモジュールをそのままimportできるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

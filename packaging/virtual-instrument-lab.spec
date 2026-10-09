# Native builds only: PyInstaller is not a cross-compiler.
import sys
from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "packaging" / "entrypoint.py")],
    pathex=[str(root)],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["Agg", "TkAgg"]}},
    excludes=["pytest", "IPython", "notebook"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="VirtualInstrumentLab", debug=False, strip=False, upx=False,
    console=sys.platform != "darwin",
    hide_console="hide-late" if sys.platform == "win32" else None,
    codesign_identity=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VirtualInstrumentLab")
if sys.platform == "darwin":
    app = BUNDLE(
        coll, name="VirtualInstrumentLab.app", icon=None,
        bundle_identifier="org.bte808.VirtualInstrumentLab",
        version="0.1.1",
        info_plist={"NSHighResolutionCapable": True},
    )

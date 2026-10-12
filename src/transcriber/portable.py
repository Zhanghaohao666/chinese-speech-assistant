"""Portable EXE entry: record startup failures instead of disappearing silently."""
from pathlib import Path
import sys,traceback,ctypes,os

def main():
    root=Path(__file__).resolve().parents[2]
    try:
        log=(root/'startup.log').open('a',encoding='utf-8',buffering=1)
        sys.stdout=sys.stderr=log
        import datetime
        print('\nStart',datetime.datetime.now().isoformat(),flush=True)
        os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
        from .app import main as application_main
        return application_main()
    except Exception:
        detail=traceback.format_exc()
        try:
            with (root/'startup.log').open('a',encoding='utf-8') as f:
                f.write(detail)
        except OSError:
            pass
        ctypes.windll.user32.MessageBoxW(None,'启动失败，请查看软件目录内的 startup.log。\n如果目录不可写，请将整个文件夹解压到桌面或其他可写目录。','wwh专属语音助手启动提示',0x10)
        return 1

if __name__=='__main__':
    sys.exit(main())

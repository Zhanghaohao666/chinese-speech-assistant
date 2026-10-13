using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using System.Reflection;
[assembly: AssemblyTitle("wwh专属语音助手")]
[assembly: AssemblyVersion("1.2.0.0")]
class PortableLauncher {
    [STAThread]
    static int Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        try {
            string exe = Path.Combine(root, "runtime", "pythonw.exe");
            if (!File.Exists(exe) || !File.Exists(Path.Combine(root,"src","transcriber","app.py")))
                throw new Exception("运行文件不完整。请先完整解压压缩包，再打开 EXE；不要只复制 EXE。");
            string command = "-u -m transcriber.portable";
            foreach (string arg in args) command += " \"" + arg.Replace("\"", "\\\"") + "\"";
            ProcessStartInfo info = new ProcessStartInfo(exe, command);
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables.Remove("QT_PLUGIN_PATH");
            info.EnvironmentVariables.Remove("QT_QPA_PLATFORM_PLUGIN_PATH");
            info.EnvironmentVariables["PATH"] = Path.Combine(root,"runtime") + ";" + Environment.GetFolderPath(Environment.SpecialFolder.System);
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            info.EnvironmentVariables["HF_HUB_DISABLE_TELEMETRY"] = "1";
            Process process = Process.Start(info);
            if (process.WaitForExit(7000) && process.ExitCode != 0)
                throw new Exception("启动失败。请查看软件目录中的 startup.log，并将日志发回排查。");
            return 0;
        } catch (Exception error) {
            MessageBox.Show(error.Message, "wwh专属语音助手启动提示", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

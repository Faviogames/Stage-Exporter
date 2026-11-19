// WRC to ACR Stage Exporter launcher: opens our window (wrcg2acr-worker.exe -m wr ui) without a console window.
// Built by 'wrcg2acr-worker.exe -m wr build-exe' with the .NET Framework compiler that ships with Windows (csc.exe).
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("WRC to ACR Stage Exporter")]
[assembly: System.Reflection.AssemblyProduct("WRC to ACR Stage Exporter")]
[assembly: System.Reflection.AssemblyDescription("WRC Generations stages for Assetto Corsa Rally")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]

static class StageStudio
{
    [STAThread]
    static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string worker = Path.Combine(root, "_internal", "wrcg2acr-worker.exe");
        if (!File.Exists(worker))
        {
            MessageBox.Show("No se encuentra _internal\\wrcg2acr-worker.exe junto a WRC to ACR Stage Exporter.exe.",
                            "WRC to ACR Stage Exporter", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        var psi = new ProcessStartInfo(worker, "-m wr ui")
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        try
        {
            Process.Start(psi);
        }
        catch (Exception e)
        {
            MessageBox.Show("No se ha podido abrir WRC to ACR Stage Exporter:\n" + e.Message, "WRC to ACR Stage Exporter",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}

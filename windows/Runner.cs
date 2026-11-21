using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Timer = System.Windows.Forms.Timer;

[assembly: AssemblyInformationalVersion("0.5.0-beta.3")]

internal static class Runner
{
    internal static readonly Icon AppIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
    internal const string Local = "http://127.0.0.1:17879";
    internal static string Root;

    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        string testRoot = Environment.GetEnvironmentVariable("FPL_RUNNER_DATA_DIR");
        Root = Path.GetFullPath(String.IsNullOrWhiteSpace(testRoot)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FPLManager")
            : testRoot);
        try
        {
            string identity;
            using (var sha = SHA256.Create())
                identity = Convert.ToBase64String(sha.ComputeHash(Encoding.UTF8.GetBytes(Root.ToUpperInvariant())))
                    .Replace('/', '_').Replace('+', '-');
            bool first;
            using (var instance = new Mutex(true, @"Local\FPLManager-" + identity, out first))
            {
                if (!first)
                {
                    MessageBox.Show("FPL Manager is already running.", "FPL Manager");
                    return;
                }
                var runtime = Path.Combine(Root, "runtime");
                foreach (var name in new[] { "fpl-manager.exe", "Microsoft.Web.WebView2.Core.dll",
                    "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll" })
                    Extract(name, Path.Combine(runtime, name), false);
                Extract("fpl.sqlite", Path.Combine(Root, "data", "fpl.sqlite"), true);
                Extract("native-model.json", Path.Combine(Root, "models", "native-model.json"), true);
                foreach (var notice in new[] { "FPL-Manager-License.txt", "WebView2-License.txt", "WebView2-Notices.txt" })
                    Extract(notice, Path.Combine(Root, "licenses", notice), false);
                AppDomain.CurrentDomain.AssemblyResolve += (sender, args) =>
                {
                    var name = new AssemblyName(args.Name).Name;
                    return name == "Microsoft.Web.WebView2.Core" || name == "Microsoft.Web.WebView2.WinForms"
                        ? Assembly.LoadFrom(Path.Combine(runtime, name + ".dll"))
                        : null;
                };
                Run(runtime);
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "FPL Manager could not start", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Run(string runtime)
    {
        using (var window = new ManagerWindow(runtime))
            Application.Run(window);
    }

    internal static Dictionary<string, object> ReadMessage(JavaScriptSerializer json, string message)
    {
        if (!message.StartsWith("{", StringComparison.Ordinal)) return null;
        try { return json.Deserialize<Dictionary<string, object>>(message); }
        catch (ArgumentException) { return null; }
        catch (InvalidOperationException) { return null; }
    }

    internal static void Extract(string resource, string destination, bool keepExisting)
    {
        if (keepExisting && File.Exists(destination))
            return;
        Directory.CreateDirectory(Path.GetDirectoryName(destination));
        var temporary = destination + ".tmp";
        using (var input = Assembly.GetExecutingAssembly().GetManifestResourceStream(resource + ".gz"))
        using (var zipped = new GZipStream(input, CompressionMode.Decompress))
        using (var output = File.Create(temporary))
            zipped.CopyTo(output);
        if (File.Exists(destination))
            File.Replace(temporary, destination, null);
        else
            File.Move(temporary, destination);
    }
}

internal sealed class ManagerWindow : Form
{
    private readonly string runtime;
    private readonly Process engine;
    private readonly HttpClient http = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(40) };
    private readonly JavaScriptSerializer json = new JavaScriptSerializer();
    private readonly WebView2 browser = new WebView2 { Dock = DockStyle.Fill };
    private readonly Label loading = new Label { Text = "Starting FPL Manager…", Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleCenter };
    private CoreWebView2Environment environment;
    private OfficialWindow official;

    internal ManagerWindow(string runtimePath)
    {
        runtime = runtimePath;
        Text = "FPL Manager";
        Icon = Runner.AppIcon;
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(1250, 850);
        MinimumSize = new Size(680, 500);
        Controls.Add(browser);
        Controls.Add(loading);
        loading.BringToFront();
        var start = new ProcessStartInfo(Path.Combine(runtime, "fpl-manager.exe"))
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Runner.Root,
        };
        start.EnvironmentVariables["FPL_PROJECT_DIR"] = Runner.Root;
        start.EnvironmentVariables["FPL_PORT"] = "17879";
        engine = Process.Start(start);
        Shown += OpenManager;
    }

    private async void OpenManager(object sender, EventArgs args)
    {
        try
        {
            using (var health = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(1) })
            {
                bool ready = false;
                for (int attempt = 0; attempt < 45 && !ready; attempt++)
                {
                    if (engine.HasExited)
                        throw new InvalidOperationException("The local engine stopped. Check that port 17879 is free.");
                    try
                    {
                        var response = await health.GetStringAsync(Runner.Local + "/api/health");
                        ready = response.Contains("\"runtime\":\"Rust\"");
                    }
                    catch (HttpRequestException) { }
                    catch (TaskCanceledException) { }
                    if (!ready) await Task.Delay(250);
                }
                if (!ready) throw new InvalidOperationException("The local engine did not start.");
            }
            if (IsDisposed) return;
            await EnsureBrowserRuntime();
            if (IsDisposed) return;
            environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Runner.Root, "browser"));
            await browser.EnsureCoreWebView2Async(environment);
            browser.CoreWebView2.AddWebResourceRequestedFilter(Runner.Local + "/*", CoreWebView2WebResourceContext.All);
            browser.CoreWebView2.WebResourceRequested += ServeAppAssets;
            browser.CoreWebView2.NavigationStarting += (s, e) => e.Cancel = !IsLocal(e.Uri);
            browser.CoreWebView2.NewWindowRequested += (s, e) =>
            {
                e.Handled = true;
                Uri uri;
                if (Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) &&
                    (uri.Scheme == "https" || IsLocal(e.Uri)))
                    Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
            };
            browser.CoreWebView2.WebMessageReceived += HandleSignIn;
            browser.Source = new Uri(Runner.Local + "/?desktop=1#/settings");
            loading.Visible = false;
        }
        catch (Exception error)
        {
            if (!IsDisposed)
            {
                MessageBox.Show(this, error.Message, "FPL Manager could not start", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
            }
        }
    }

    private void ServeAppAssets(object sender, CoreWebView2WebResourceRequestedEventArgs args)
    {
        if (args.Request.Method != "GET" || !IsLocal(args.Request.Uri)) return;
        var path = new Uri(args.Request.Uri).AbsolutePath;
        string resource, contentType;
        switch (path)
        {
            case "/": resource = "index.html"; contentType = "text/html"; break;
            case "/app.css": resource = "app.css"; contentType = "text/css"; break;
            case "/app.js": resource = "app.js"; contentType = "text/javascript"; break;
            default: return;
        }
        var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(resource);
        if (stream != null)
            args.Response = environment.CreateWebResourceResponse(stream, 200, "OK",
                "Content-Type: " + contentType + "; charset=utf-8\r\nCache-Control: no-store");
    }

    private async Task EnsureBrowserRuntime()
    {
        try
        {
            if (!String.IsNullOrEmpty(CoreWebView2Environment.GetAvailableBrowserVersionString()))
                return;
        }
        catch (WebView2RuntimeNotFoundException) { }
        loading.Text = "Installing the Microsoft WebView2 Runtime…";
        var setup = Path.Combine(runtime, "MicrosoftEdgeWebview2Setup.exe");
        Runner.Extract("MicrosoftEdgeWebview2Setup.exe", setup, false);
        using (var installer = Process.Start(new ProcessStartInfo(setup, "/silent /install")
        {
            UseShellExecute = false, CreateNoWindow = true,
        }))
        {
            if (!await Task.Run(() => installer.WaitForExit(180000)) || installer.ExitCode != 0)
                throw new InvalidOperationException("The Microsoft WebView2 Runtime setup did not complete. Check your internet connection and try again.");
        }
    }

    private static bool IsLocal(string source)
    {
        Uri uri;
        return Uri.TryCreate(source, UriKind.Absolute, out uri) &&
            uri.GetLeftPart(UriPartial.Authority) == Runner.Local;
    }

    private void HandleSignIn(object sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (!IsLocal(args.Source)) return;
        var request = Runner.ReadMessage(json, args.WebMessageAsJson);
        object type, value, generation;
        if (request == null || !request.TryGetValue("type", out type)) return;
        if (Equals(type, "fpl-review-transfers"))
        {
            if (request.TryGetValue("plan", out value) && value is Dictionary<string, object>)
                OpenTransferReview((Dictionary<string, object>)value);
            return;
        }
        if (!Equals(type, "fpl-sign-in") || !request.TryGetValue("url", out value) ||
            !request.TryGetValue("generation", out generation) ||
            !(generation is int)) return;
        Uri uri;
        if (!Uri.TryCreate(value as string, UriKind.Absolute, out uri) || !OfficialWindow.IsOfficial(uri.AbsoluteUri))
            return;
        var challenge = Regex.Match(uri.Fragment, @"^#fpl-local=([a-f0-9]{64})&port=17879&prices=0$");
        if (!challenge.Success || uri.AbsolutePath != "/transfers") return;

        if (official != null) official.Close();
        var signIn = new OfficialWindow(environment, http, uri, challenge.Groups[1].Value);
        official = signIn;
        signIn.FormClosed += (s, e) =>
        {
            if (official == signIn) official = null;
            if (signIn.Succeeded || IsDisposed || Disposing || browser.CoreWebView2 == null) return;
            browser.CoreWebView2.PostWebMessageAsJson(json.Serialize(new Dictionary<string, object>
            {
                { "type", "fpl-sign-in-error" }, { "generation", generation },
                { "message", signIn.Error ?? "FPL sign-in closed. Click Connect to try again." },
            }));
        };
        signIn.Show(this);
    }

    private void OpenTransferReview(Dictionary<string, object> plan)
    {
        if (official != null) official.Close();
        var review = new OfficialWindow(environment, http, new Uri("https://fantasy.premierleague.com/transfers"), null, plan);
        official = review;
        review.FormClosed += (s, e) =>
        {
            if (official == review) official = null;
            if (IsDisposed || Disposing || browser.CoreWebView2 == null) return;
            browser.CoreWebView2.PostWebMessageAsJson(json.Serialize(new Dictionary<string, object>
            {
                { "type", "fpl-transfer-review-finished" }, { "verified", review.Succeeded },
                { "message", review.Error },
            }));
        };
        review.Show(this);
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        if (official != null) official.Close();
        if (!engine.HasExited) engine.Kill();
        engine.Dispose();
        http.Dispose();
        base.OnFormClosed(e);
    }
}

internal sealed class OfficialWindow : Form
{
    private readonly CoreWebView2Environment environment;
    private readonly HttpClient http;
    private readonly Uri page;
    private readonly string token;
    private readonly Dictionary<string, object> transferPlan;
    private bool transferPrepared;
    private bool transferStagingStopped;
    private readonly JavaScriptSerializer json = new JavaScriptSerializer();
    private readonly WebView2 web = new WebView2 { Dock = DockStyle.Fill };
    private readonly Label address = new Label { Text = "Sign in to your official FPL account", Dock = DockStyle.Top,
        Height = 34, TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(10, 0, 0, 0) };
    private readonly Timer retry = new Timer { Interval = 2500 };
    private bool submitting;
    internal bool Succeeded { get; private set; }
    internal string Error { get; private set; }

    internal OfficialWindow(CoreWebView2Environment environment, HttpClient http, Uri page, string token,
        Dictionary<string, object> transferPlan = null)
    {
        this.environment = environment;
        this.http = http;
        this.page = page;
        this.token = token;
        this.transferPlan = transferPlan;
        Icon = Runner.AppIcon;
        Text = transferPlan == null ? "Official Fantasy Premier League sign-in" : "Review transfers on official FPL";
        StartPosition = FormStartPosition.CenterParent;
        ClientSize = transferPlan == null ? new Size(880, 730) : new Size(1240, 780);
        if (transferPlan != null) WindowState = FormWindowState.Maximized;
        Controls.Add(web);
        Controls.Add(address);
        Shown += LoadPage;
        retry.Tick += async (sender, args) => await ReadAccount();
    }

    internal static bool IsOfficial(string value)
    {
        Uri uri;
        return Uri.TryCreate(value, UriKind.Absolute, out uri) &&
            uri.GetLeftPart(UriPartial.Authority) == "https://fantasy.premierleague.com";
    }

    private async void LoadPage(object sender, EventArgs args)
    {
        try
        {
            await web.EnsureCoreWebView2Async(environment);
            if (IsDisposed) return;
            web.CoreWebView2.NavigationStarting += (s, e) =>
            {
                Uri uri;
                e.Cancel = !Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) || uri.Scheme != "https";
                if (!e.Cancel && !transferStagingStopped) address.Text = uri.GetLeftPart(UriPartial.Authority);
            };
            web.CoreWebView2.NewWindowRequested += (s, e) =>
            {
                e.Handled = true;
                Uri uri;
                if (Uri.TryCreate(e.Uri, UriKind.Absolute, out uri) && uri.Scheme == "https")
                    web.CoreWebView2.Navigate(uri.AbsoluteUri);
            };
            if (transferPlan == null) web.CoreWebView2.WebMessageReceived += SubmitAccount;
            else web.CoreWebView2.WebMessageReceived += ObserveTransferReview;
            web.CoreWebView2.NavigationCompleted += async (s, e) => { if (e.IsSuccess) await ReadAccount(); };
            // The one-use token stays in the native host.
            web.CoreWebView2.Navigate(page.GetLeftPart(UriPartial.Path));
            retry.Start();
        }
        catch (Exception error)
        {
            if (!IsDisposed) { Error = error.Message; Close(); }
        }
    }

    private async Task ReadAccount()
    {
        if (submitting || IsDisposed || web.CoreWebView2 == null || !IsOfficial(web.CoreWebView2.Source)) return;
        try
        {
            if (transferStagingStopped) return;
            var resource = transferPlan == null ? "import-fpl.js" : "review-transfers.js";
            using (var input = Assembly.GetExecutingAssembly().GetManifestResourceStream(resource))
            using (var text = new StreamReader(input))
            {
                var script = text.ReadToEnd();
                if (transferPlan != null)
                    script = "(" + script + ")(" + json.Serialize(transferPlan) + "," +
                        (transferPrepared ? "false" : "true") + ")";
                await web.CoreWebView2.ExecuteScriptAsync(script);
            }
        }
        catch (InvalidOperationException) { }
        catch (System.Runtime.InteropServices.COMException) { }
    }

    private void ObserveTransferReview(object sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (!IsOfficial(args.Source) || !IsOfficial(web.CoreWebView2.Source) || transferStagingStopped) return;
        var values = Runner.ReadMessage(json, args.WebMessageAsJson);
        object type, status;
        if (values == null || !values.TryGetValue("type", out type) || !Equals(type, "fpl-transfer-review") ||
            !values.TryGetValue("status", out status)) return;
        if (Equals(status, "prepared"))
        {
            transferPrepared = true;
            address.Text = "Review the players and points cost on official FPL, then choose Confirm.";
        }
        else if (Equals(status, "verified") && transferPrepared)
        {
            Succeeded = true;
            Close();
        }
        else if (Equals(status, "error"))
        {
            object message, reset;
            Error = values.TryGetValue("message", out message) ? message as string : null;
            transferStagingStopped = true;
            if (values.TryGetValue("reset", out reset) && Equals(reset, true))
                web.CoreWebView2.Navigate("https://fantasy.premierleague.com/transfers");
            address.Text = Error ?? "FPL could not stage these transfers.";
        }
    }

    private async void SubmitAccount(object sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (submitting || !IsOfficial(args.Source) || !IsOfficial(web.CoreWebView2.Source)) return;
        var values = Runner.ReadMessage(json, args.WebMessageAsJson);
        object type, reference, prices;
        if (values == null || !values.TryGetValue("type", out type) || !Equals(type, "fpl-account") ||
            !values.TryGetValue("reference", out reference) || !(reference is int) ||
            !values.TryGetValue("sale_prices", out prices)) return;
        submitting = true;
        address.Text = "Verifying your team and loading the squad…";
        try
        {
            object bank, free;
            values.TryGetValue("bank", out bank);
            values.TryGetValue("free_transfers", out free);
            var body = new Dictionary<string, object>
            {
                { "token", token }, { "reference", reference }, { "sale_prices", prices },
                { "bank", bank }, { "free_transfers", free },
            };
            using (var request = new StringContent(json.Serialize(body), Encoding.UTF8, "application/json"))
            using (var response = await http.PostAsync(Runner.Local + "/api/connect/complete", request))
            {
                if (IsDisposed) return;
                if (response.IsSuccessStatusCode) Succeeded = true;
                else
                {
                    var error = json.Deserialize<Dictionary<string, object>>(await response.Content.ReadAsStringAsync());
                    object detail;
                    Error = error != null && error.TryGetValue("error", out detail)
                        ? Convert.ToString(detail) : "Could not verify the FPL account.";
                }
            }
        }
        catch (Exception error)
        {
            Error = error.Message;
        }
        if (!IsDisposed) Close();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) retry.Dispose();
        base.Dispose(disposing);
    }
}

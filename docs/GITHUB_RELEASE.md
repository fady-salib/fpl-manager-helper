# Publishing FPL Manager

1. Extract `dist/github/fpl-manager-source.zip` and upload the contents of
   its root to the GitHub repository.
2. Check the Test and lint workflow on the default branch before tagging a release.
3. Create a release for the version in `rust/Cargo.toml`, `rust/Cargo.lock` and
   the Windows runner's product version. Attach `FPL Manager.exe` from the
   project root and `dist/github/SHA256SUMS.txt` to the release.
4. List the checks completed for that build in the release notes.

The source bundle excludes user data, reports, credentials, virtual environments,
compiled binaries, cached snapshots and trained weights. The release EXE includes
a public seed database, the fitted model and the Microsoft WebView2 bootstrapper.

To rebuild the Windows release, build the Rust engine with
`cargo build --manifest-path rust/Cargo.toml --locked --release`. Provide a public
`data/fpl.sqlite`, a compatible `models/native-model.json` and an unpacked
Microsoft WebView2 SDK. Place the official `MicrosoftEdgeWebview2Setup.exe`
bootstrapper in the SDK directory and run
`./windows/build-runner.ps1 -WebViewSdk <sdk-directory>`.

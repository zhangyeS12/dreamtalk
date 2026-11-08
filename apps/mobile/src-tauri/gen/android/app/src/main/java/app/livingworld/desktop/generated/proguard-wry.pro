# THIS FILE IS AUTO-GENERATED. DO NOT MODIFY!!

# Copyright 2020-2023 Tauri Programme within The Commons Conservancy
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

-keep class app.livingworld.desktop.* {
  native <methods>;
}

-keep class app.livingworld.desktop.WryActivity {
  public <init>(...);

  void setWebView(app.livingworld.desktop.RustWebView);
  java.lang.Class getAppClass(...);
  int getId();
  java.lang.String getVersion();
  int startActivity(...);
}

-keep class app.livingworld.desktop.Ipc {
  public <init>(...);

  @android.webkit.JavascriptInterface public <methods>;
}

-keep class app.livingworld.desktop.RustWebView {
  public <init>(...);

  void loadUrlMainThread(...);
  void loadHTMLMainThread(...);
  void evalScript(...);
}

-keep class app.livingworld.desktop.RustWebChromeClient,app.livingworld.desktop.RustWebViewClient {
  public <init>(...);
}

import type { CapacitorConfig } from "@capacitor/cli";

/**
 * The iOS app is a Capacitor shell around the hosted WorkAtlas site.
 *
 * EJP_APP_URL must be a public HTTPS deployment of this repository. The shell
 * cannot run the FastAPI server on the device, so `app.workatlas.pro` below is
 * only a placeholder. Set the real domain before building for TestFlight:
 *
 *   PowerShell:  $env:EJP_APP_URL = "https://jobs.example.com"
 *   macOS shell: export EJP_APP_URL="https://jobs.example.com"
 */
const appUrl = (process.env.EJP_APP_URL || "https://app.workatlas.pro").replace(/\/+$/, "");
const host = new URL(appUrl).hostname;

const config: CapacitorConfig = {
  appId: "com.workatlas.app",
  appName: "WorkAtlas",
  webDir: "www",
  backgroundColor: "#0b1220",
  server: {
    url: appUrl,
    hostname: host,
    cleartext: false,
    errorPath: "offline.html",
    // Same-origin app pages stay in the WebView. Any other host opens in the
    // system browser, so employer application links never trap the user.
    allowNavigation: [host, `*.${host}`]
  },
  ios: {
    contentInset: "never",
    scrollEnabled: true,
    backgroundColor: "#0b1220",
    preferredContentMode: "mobile",
    limitsNavigationsToAppBoundDomains: false
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 900,
      launchAutoHide: true,
      backgroundColor: "#0b1220",
      showSpinner: false,
      fadeOutDuration: 220,
      splashFullScreen: true,
      splashImmersive: true
    },
    StatusBar: {
      overlaysWebView: true,
      style: "DEFAULT",
      backgroundColor: "#0b1220"
    },
    Keyboard: {
      resize: "body",
      style: "DEFAULT",
      resizeOnFullScreen: true
    },
    PushNotifications: {
      presentationOptions: ["badge", "sound", "alert"]
    }
  }
};

export default config;

import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId:   "com.ftthplanner.app",
  appName: "FTTH GIS Planner",
  webDir:  ".",
  server: { androidScheme: "https" },
  ios: {
    contentInset: "always",
    backgroundColor: "#04090F",
    scrollEnabled: false
  },
  android: {
    backgroundColor: "#04090F",
    allowMixedContent: true
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      backgroundColor: "#04090F",
      showSpinner: false
    },
    StatusBar: {
      style: "DARK",
      backgroundColor: "#04090F"
    }
  }
};

export default config;

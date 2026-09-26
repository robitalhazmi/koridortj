/**
 * Apache Superset Embedded SDK (Clean Optimized Build for KoridorTJ)
 * Supports JWT Guest Token authentication, responsive embedding, and iframe communications.
 */
(function (global, factory) {
  if (typeof exports === "object" && typeof module !== "undefined") {
    module.exports = factory();
  } else if (typeof define === "function" && define.amd) {
    define([], factory);
  } else {
    global.supersetEmbeddedSdk = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : window, function () {
  "use strict";

  const COMM_TYPE = "__embedded_comms__";
  const FILTER_CONFIG_MAP = {
    visible: "show_filters",
    expanded: "expand_filters",
  };

  const Actions = {
    GET: "get",
    REPLY: "reply",
    EMIT: "emit",
    ERROR: "error",
  };

  class Switchboard {
    constructor(options) {
      this.port = undefined;
      this.name = "superset-embedded-sdk";
      this.methods = {};
      this.incrementor = 1;
      this.debugMode = false;
      this.isInitialised = false;
      if (options) this.init(options);
    }

    init({ port, name = "switchboard", debug = false }) {
      if (this.isInitialised) return;
      this.port = port;
      this.name = name;
      this.debugMode = debug;
      this.port.addEventListener("message", async (event) => {
        const data = event.data;
        if (data && data.switchboardAction === Actions.GET) {
          this.port.postMessage(await this.getMethodResult(data));
        } else if (data && data.switchboardAction === Actions.EMIT) {
          const { method, args } = data;
          const fn = this.methods[method];
          if (fn) fn(args);
        }
      });
      this.isInitialised = true;
    }

    async getMethodResult({ messageId, method, args }) {
      const fn = this.methods[method];
      if (!fn) {
        return {
          switchboardAction: Actions.ERROR,
          messageId,
          error: `[${this.name}] Method "${method}" is not defined`,
        };
      }
      try {
        const result = await fn(args);
        return { switchboardAction: Actions.REPLY, messageId, result };
      } catch (err) {
        return {
          switchboardAction: Actions.ERROR,
          messageId,
          error: `[${this.name}] Method "${method}" threw an error: ${err}`,
        };
      }
    }

    defineMethod(method, fn) {
      this.methods[method] = fn;
    }

    get(method, args) {
      return new Promise((resolve, reject) => {
        if (!this.isInitialised) return reject(new Error("Switchboard not initialised"));
        const messageId = `m_${this.name}_${this.incrementor++}`;
        const handler = (event) => {
          const data = event.data;
          if (data && data.messageId === messageId) {
            this.port.removeEventListener("message", handler);
            if (data.switchboardAction === Actions.REPLY) {
              resolve(data.result);
            } else {
              reject(new Error(data.error || "Unexpected response message"));
            }
          }
        };
        this.port.addEventListener("message", handler);
        this.port.start();
        this.port.postMessage({
          switchboardAction: Actions.GET,
          method,
          messageId,
          args,
        });
      });
    }

    emit(method, args) {
      if (!this.isInitialised) return;
      this.port.postMessage({
        switchboardAction: Actions.EMIT,
        method,
        args,
      });
    }

    start() {
      if (this.isInitialised) this.port.start();
    }
  }

  function getExpirationLeadTime(token) {
    try {
      const parts = token.split(".");
      if (parts.length < 2) return 300000;
      const payloadStr = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
      const payload = JSON.parse(payloadStr);
      const expMs = (typeof payload.exp === "number" ? payload.exp : parseFloat(payload.exp)) * 1000;
      if (!isNaN(expMs)) {
        return Math.max(10000, expMs - Date.now()) - 5000;
      }
    } catch (e) {
      // ignore
    }
    return 300000;
  }

  function buildUiConfig(config) {
    let flags = 0;
    if (config) {
      if (config.hideTitle) flags += 1;
      if (config.hideTab) flags += 2;
      if (config.hideChartControls) flags += 8;
      if (config.emitDataMasks) flags += 16;
      if (config.showRowLimitWarning) flags += 32;
    }
    return flags;
  }

  async function embedDashboard({
    id,
    supersetDomain,
    mountPoint,
    fetchGuestToken,
    dashboardUiConfig,
    debug = false,
    iframeTitle = "Embedded Superset Dashboard",
    iframeSandboxExtras = [],
    iframeAllowExtras = [],
    referrerPolicy,
    resolvePermalinkUrl,
    guestTokenFetchTimeoutMs = 30000,
  }) {
    const domain = supersetDomain.replace(/\/+$/, "");

    async function fetchTokenWithTimeout() {
      const tokenPromise = fetchGuestToken();
      let timer;
      const timeoutPromise = new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(`fetchGuestToken did not resolve within ${guestTokenFetchTimeoutMs}ms`)),
          guestTokenFetchTimeoutMs
        );
      });
      return Promise.race([tokenPromise, timeoutPromise]).finally(() => clearTimeout(timer));
    }

    let refreshTimer;
    let isUnmounted = false;

    const [initialToken, switchboard] = await Promise.all([
      fetchTokenWithTimeout(),
      new Promise((resolve) => {
        const iframe = document.createElement("iframe");
        const uiNum = buildUiConfig(dashboardUiConfig);
        const filters = dashboardUiConfig?.filters || {};
        const params = new URLSearchParams();

        if (uiNum > 0) params.set("uiConfig", String(uiNum));
        Object.entries(filters).forEach(([k, v]) => {
          const paramKey = FILTER_CONFIG_MAP[k] || k;
          params.set(paramKey, String(v));
        });

        if (dashboardUiConfig?.urlParams) {
          Object.entries(dashboardUiConfig.urlParams).forEach(([k, v]) => {
            params.set(k, String(v));
          });
        }

        const queryStr = params.toString() ? "?" + params.toString() : "";

        // Standard secure sandbox flags
        [
          "allow-same-origin",
          "allow-scripts",
          "allow-presentation",
          "allow-downloads",
          "allow-forms",
          "allow-popups",
          ...iframeSandboxExtras,
        ].forEach((flag) => iframe.sandbox.add(flag));

        if (referrerPolicy) iframe.referrerPolicy = referrerPolicy;

        // Apply styling cleanly before mounting to prevent layout shifting
        iframe.style.width = "100%";
        iframe.style.height = "100%";
        iframe.style.minHeight = "850px";
        iframe.style.border = "none";
        iframe.style.display = "block";
        iframe.style.background = "transparent";
        iframe.title = iframeTitle;

        // Supported standard permissions
        const allowFeatures = Array.from(new Set(["fullscreen", ...iframeAllowExtras]));
        iframe.setAttribute("allow", allowFeatures.join("; "));

        iframe.addEventListener("load", () => {
          const channel = new MessageChannel();
          iframe.contentWindow.postMessage(
            { type: COMM_TYPE, handshake: "port transfer" },
            domain,
            [channel.port2]
          );
          resolve(new Switchboard({ port: channel.port1, name: "superset-embedded-sdk", debug }));
        });

        iframe.src = `${domain}/embedded/${id}${queryStr}`;
        mountPoint.replaceChildren(iframe);
      }),
    ]);

    switchboard.emit("guestToken", { guestToken: initialToken });

    async function scheduleRefresh(token) {
      if (isUnmounted) return;
      try {
        const nextToken = await fetchTokenWithTimeout();
        if (isUnmounted) return;
        switchboard.emit("guestToken", { guestToken: nextToken });
        refreshTimer = setTimeout(() => scheduleRefresh(nextToken), getExpirationLeadTime(nextToken));
      } catch (err) {
        if (!isUnmounted) {
          refreshTimer = setTimeout(() => scheduleRefresh(token), 10000);
        }
      }
    }

    refreshTimer = setTimeout(() => scheduleRefresh(initialToken), getExpirationLeadTime(initialToken));
    switchboard.start();

    if (resolvePermalinkUrl) {
      switchboard.defineMethod("resolvePermalinkUrl", async ({ key }) => {
        try {
          return await resolvePermalinkUrl({ key });
        } catch (e) {
          return null;
        }
      });
    }

    return {
      getScrollSize: () => switchboard.get("getScrollSize"),
      unmount: function () {
        isUnmounted = true;
        if (refreshTimer) clearTimeout(refreshTimer);
        mountPoint.replaceChildren();
      },
      getDashboardPermalink: (anchor) => switchboard.get("getDashboardPermalink", { anchor }),
      getActiveTabs: () => switchboard.get("getActiveTabs"),
      observeDataMask: (fn) => switchboard.defineMethod("observeDataMask", fn),
      getDataMask: () => switchboard.get("getDataMask"),
      getChartStates: () => switchboard.get("getChartStates"),
      getChartDataPayloads: (e) => switchboard.get("getChartDataPayloads", e),
      setThemeConfig: (cfg) => switchboard.emit("setThemeConfig", { themeConfig: cfg }),
      setThemeMode: (mode) => switchboard.emit("setThemeMode", { mode }),
    };
  }

  return { embedDashboard };
});
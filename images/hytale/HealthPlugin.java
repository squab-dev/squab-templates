package dev.squab.hytale;

import com.hypixel.hytale.server.core.HytaleServer;
import com.hypixel.hytale.server.core.auth.ServerAuthManager;
import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import com.hypixel.hytale.server.core.universe.Universe;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.TimeUnit;
import com.hypixel.hytale.common.util.java.ManifestUtil;
import com.hypixel.hytale.server.core.update.UpdateService;


/** Loopback-only readiness; never exposes tokens, profiles or world contents. */
public final class HealthPlugin extends JavaPlugin {
    private HttpServer http;
    private volatile boolean updateChecked;
    private Thread updater;
    public HealthPlugin(JavaPluginInit init) { super(init); }

    @Override
    protected void start() {
        try {
            http = HttpServer.create(new InetSocketAddress("127.0.0.1", 5521), 8);
            http.createContext("/ready", exchange -> {
                try {
                    if (!exchange.getRequestMethod().equals("GET")
                            || !exchange.getRequestURI().toString().equals("/ready")) {
                        exchange.sendResponseHeaders(404, -1);
                        return;
                    }
                    boolean ready = ready();
                    byte[] body = (ready ? "{\"ready\":true}" : "{\"ready\":false}")
                        .getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set("Content-Type", "application/json");
                    exchange.sendResponseHeaders(ready ? 200 : 503, body.length);
                    exchange.getResponseBody().write(body);
                } finally {
                    exchange.close();
                }
            });
            http.start();
            updater = Thread.ofVirtual().name("squab-startup-update").start(this::checkStartupUpdate);
        } catch (IOException failure) {
            throw new IllegalStateException("Cannot start Squab readiness endpoint", failure);
        }
    }

    private void checkStartupUpdate() {
        try {
            // Device login may still be pending. Never advertise readiness until
            // the owner's session has checked the official release channel.
            while (!baseReady()) {
                if (HytaleServer.get().isShuttingDown()) return;
                Thread.sleep(1000);
            }
            System.out.println("[Squab] Checking for Hytale release updates.");
            UpdateService service = new UpdateService();
            var manifest = service.checkForUpdate("release").get(45, TimeUnit.SECONDS);
            if (manifest == null) throw new IllegalStateException("No release manifest");
            if (manifest.version.equals(ManifestUtil.getImplementationVersion())) {
                System.out.println("[Squab] Hytale release is up to date.");
                updateChecked = true;
                return;
            }
            System.out.println("[Squab] Downloading and verifying the latest Hytale release.");
            var task = service.downloadUpdate(manifest, UpdateService.getStagingDir(), (percent, downloaded, total) -> {});
            if (!Boolean.TRUE.equals(task.future().get(600, TimeUnit.SECONDS)))
                throw new IllegalStateException("Release download failed");
            // The image wrapper requests the official apply command, then
            // replaces staged files only after the server has shut down.
            System.out.println("[Squab] UPDATE_READY");
        } catch (InterruptedException stopped) {
            Thread.currentThread().interrupt();
        } catch (Exception failure) {
            System.err.println("[Squab] Hytale update check/download failed. Restart to retry; installed files are preserved.");
        }
    }

    private boolean ready() { return updateChecked && baseReady(); }

    private boolean baseReady() {
        HytaleServer server = HytaleServer.get();
        Universe universe = Universe.get();
        ServerAuthManager auth = ServerAuthManager.getInstance();
        return server != null && server.isBooted() && !server.isShuttingDown()
            && universe != null && universe.getUniverseReady().isDone()
            && !universe.getUniverseReady().isCompletedExceptionally()
            && universe.getDefaultWorld() != null
            && auth.hasSessionToken() && auth.hasIdentityToken()
            && auth.getTokenExpiry() != null && auth.getTokenExpiry().isAfter(Instant.now());
    }

    @Override
    protected void shutdown() {
        if (updater != null) updater.interrupt();
        if (http != null) http.stop(0);
    }
}

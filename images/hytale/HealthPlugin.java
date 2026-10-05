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

/** Loopback-only readiness; never exposes tokens, profiles or world contents. */
public final class HealthPlugin extends JavaPlugin {
    private HttpServer http;
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
        } catch (IOException failure) {
            throw new IllegalStateException("Cannot start Squab readiness endpoint", failure);
        }
    }

    private boolean ready() {
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
        if (http != null) http.stop(0);
    }
}

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;
import java.io.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class WebGateway {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);
        server.createContext("/api/predict", new PredictHandler());
        server.setExecutor(null);
        System.out.println("WebGateway escuchando en el puerto 8080...");
        server.start();
    }

    static class PredictHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            // Configurar CORS para que el navegador del Integrante 3 no bloquee la petición
            exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
            exchange.getResponseHeaders().add("Access-Control-Allow-Methods", "POST, OPTIONS");
            exchange.getResponseHeaders().add("Access-Control-Allow-Headers", "Content-Type");

            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(204, -1);
                return;
            }

            if ("POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                InputStream is = exchange.getRequestBody();
                String pixels = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                
                String clientId = "web-client";
                System.out.println("Petición HTTP recibida del cliente Web.");
                
                // Llamamos a la lógica de RabbitMQ que ya creamos en CentralServer
                // (Asegúrate de haber puesto 'public static' a procesarConRabbitMQ en CentralServer)
                String resultTCP = CentralServer.procesarConRabbitMQ(clientId, pixels);
                
                // Convertimos "RESULT|id|1|3|0.9,0.05,0.05" a un JSON
                String respuestaJson = convertirTCPaJSON(resultTCP);

                exchange.getResponseHeaders().add("Content-Type", "application/json");
                byte[] response = respuestaJson.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, response.length);
                OutputStream os = exchange.getResponseBody();
                os.write(response);
                os.close();
            } else {
                exchange.sendResponseHeaders(405, -1); 
            }
        }
    }

    // Método auxiliar para que el Web reciba un JSON bonito en lugar del texto con "|"
    private static String convertirTCPaJSON(String tcpResult) {
        try {
            if (tcpResult.startsWith("RESULT")) {
                String[] parts = tcpResult.split("\\|");
                String[] probs = parts[4].split(",");
                return String.format(
                    "{\"status\":\"OK\", \"probabilidades\": {\"circulo\": %s, \"cruz\": %s, \"triangulo\": %s}}",
                    probs[0], probs[1], probs[2]
                );
            } else {
                return "{\"status\":\"ERROR\", \"mensaje\": \"" + tcpResult + "\"}";
            }
        } catch (Exception e) {
            return "{\"status\":\"ERROR\", \"mensaje\":\"Error parseando respuesta\"}";
        }
    }
}
package messaging;

import com.rabbitmq.client.*;
import com.google.gson.*;
import models.MensajesRabbit;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

/** One publisher channel guarded by synchronization; independent consumer channel. */
public class RabbitMQManager implements AutoCloseable {
    private final Gson gson = new Gson();
    private final ConcurrentHashMap<String, CompletableFuture<MensajesRabbit.RespuestaIA>> pending = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String,String> clients = new ConcurrentHashMap<>();
    private final Connection connection;
    private final Channel publisher;
    private final Channel consumer;
    private final int requestTimeout = setting("RABBITMQ_REQUEST_TIMEOUT_MS", 25000, 100, 119000);
    private final int confirmTimeout = setting("RABBITMQ_CONFIRM_TIMEOUT_MS", 5000, 100, 60000);
    public int requestTimeoutMs() { return requestTimeout; }

    private static int setting(String key, int fallback, int minimum, int maximum) {
        int value = Integer.parseInt(env(key, Integer.toString(fallback)));
        if (value < minimum || value > maximum) throw new IllegalArgumentException("invalid_" + key);
        return value;
    }
    private final String requests = env("IA_REQUEST_QUEUE", "cola_modeloA");
    private final String results = env("IA_RESULT_QUEUE", "cola_resultadosA");

    private static String env(String key, String fallback) {
        return System.getenv().getOrDefault(key, fallback);
    }
    public RabbitMQManager(String host, int port) throws Exception {
        ConnectionFactory factory = new ConnectionFactory();
        factory.setHost(host);
        factory.setPort(port);
        String user = env("RABBITMQ_USER", ""), password = env("RABBITMQ_PASSWORD", "");
        if (user.isEmpty() || password.isEmpty()) throw new IllegalArgumentException("rabbitmq_credentials_required");
        factory.setUsername(user);
        factory.setPassword(password);
        factory.setVirtualHost(env("RABBITMQ_VHOST", "/"));
        factory.setConnectionTimeout(setting("RABBITMQ_CONNECT_TIMEOUT_MS", 5000, 100, 60000));
        factory.setRequestedHeartbeat(setting("RABBITMQ_HEARTBEAT", 60, 10, 600));
        connection = factory.newConnection();
        try {
            publisher = connection.createChannel();
            consumer = connection.createChannel();
            publisher.queueDeclare(requests, true, false, false, null);
            consumer.queueDeclare(results, true, false, false, null);
            publisher.confirmSelect();
            consumer.basicQos(32);
            consumer.basicConsume(results, false, (tag, delivery) -> {
                try {
                    JsonObject json=JsonParser.parseString(new String(delivery.getBody(),StandardCharsets.UTF_8)).getAsJsonObject();
                    if(!json.has("schemaVersion") || !"1".equals(json.get("schemaVersion").toString()))
                        throw new IllegalArgumentException("schema_version");
                    MensajesRabbit.RespuestaIA response = gson.fromJson(json, MensajesRabbit.RespuestaIA.class);
                    if (response == null || response.schemaVersion != 1 || response.idSolicitud == null
                        || !response.idSolicitud.equals(delivery.getProperties().getCorrelationId()))
                        throw new IllegalArgumentException("invalid_response_correlation");
                    if(!"RESULTADO_CLASIFICACION".equals(response.tipo)||!"A".equals(response.modeloDestino)
                        || (clients.containsKey(response.idSolicitud)&&!clients.get(response.idSolicitud).equals(response.idCliente)))
                        throw new IllegalArgumentException("invalid_response_identity");
                    CompletableFuture<MensajesRabbit.RespuestaIA> future = pending.remove(response.idSolicitud);
                    if (future != null) {clients.remove(response.idSolicitud);future.complete(response);}
                    consumer.basicAck(delivery.getEnvelope().getDeliveryTag(), false);
                } catch (RuntimeException invalid) {
                    consumer.basicReject(delivery.getEnvelope().getDeliveryTag(), false);
                    System.err.println("Respuesta RabbitMQ invalida rechazada");
                }
            }, tag -> pending.values().forEach(f -> f.completeExceptionally(new IllegalStateException("consumer_cancelled"))));
        } catch (Exception failure) { connection.close(); throw failure; }
    }
    public synchronized CompletableFuture<MensajesRabbit.RespuestaIA> enviarTarea(MensajesRabbit.PeticionIA request) throws Exception {
        CompletableFuture<MensajesRabbit.RespuestaIA> future = new CompletableFuture<>();
        if (pending.putIfAbsent(request.idSolicitud, future) != null)
            throw new IllegalArgumentException("duplicate_request_id_in_flight");
        clients.put(request.idSolicitud,request.idCliente);
        future.orTimeout(requestTimeout, TimeUnit.MILLISECONDS).whenComplete((result, error) -> {
            if(pending.remove(request.idSolicitud, future))clients.remove(request.idSolicitud);
        });
        try {
            publisher.basicPublish("", requests, new AMQP.BasicProperties.Builder()
                .contentType("application/json").deliveryMode(2).correlationId(request.idSolicitud)
                .messageId(request.idSolicitud).build(), gson.toJson(request).getBytes(StandardCharsets.UTF_8));
            publisher.waitForConfirmsOrDie(confirmTimeout);
        } catch (Exception failure) {
            pending.remove(request.idSolicitud, future);clients.remove(request.idSolicitud);
            future.completeExceptionally(failure);
            throw failure;
        }
        return future;
    }
    public void cancelar(String id) {
        CompletableFuture<MensajesRabbit.RespuestaIA> future = pending.remove(id);
        if (future != null) {clients.remove(id);future.cancel(false);}
    }
    public void close() throws Exception {
        pending.values().forEach(f -> f.cancel(false));
        pending.clear();clients.clear();
        connection.close();
    }
}

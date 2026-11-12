package messaging;

import com.rabbitmq.client.*;
import com.google.gson.Gson;
import models.MensajesRabbit;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class RabbitMQManager {
    private static final String QUEUE_MODEL_A = "cola_modeloA";
    private static final String QUEUE_RESULT_A = "cola_resultadosA";
    
    private final ConnectionFactory factory;
    private final Gson gson = new Gson();
    
    private final ConcurrentHashMap<String, CompletableFuture<MensajesRabbit.RespuestaIA>> peticionesEnVuelo = new ConcurrentHashMap<>();

    public RabbitMQManager(String host, int port) throws Exception {
        factory = new ConnectionFactory();
        factory.setHost(host);
        factory.setPort(port);
        
        iniciarConsumidor();
    }

    public CompletableFuture<MensajesRabbit.RespuestaIA> enviarTarea(MensajesRabbit.PeticionIA peticion) throws Exception {
        CompletableFuture<MensajesRabbit.RespuestaIA> futuro = new CompletableFuture<>();
        peticionesEnVuelo.put(peticion.idSolicitud, futuro);

        try (Connection connection = factory.newConnection();
             Channel channel = connection.createChannel()) {
            
            channel.queueDeclare(QUEUE_MODEL_A, true, false, false, null);
            
            String json = gson.toJson(peticion);
            AMQP.BasicProperties props = new AMQP.BasicProperties.Builder()
                    .deliveryMode(2) 
                    .contentType("application/json")
                    .build();

            channel.basicPublish("", QUEUE_MODEL_A, props, json.getBytes(StandardCharsets.UTF_8));
            System.out.println(" [x] Enviado a RabbitMQ: " + peticion.idSolicitud);
        }
        return futuro;
    }

    private void iniciarConsumidor() throws Exception {
        Connection connection = factory.newConnection();
        Channel channel = connection.createChannel();
        channel.queueDeclare(QUEUE_RESULT_A, true, false, false, null);
        
        DeliverCallback deliverCallback = (consumerTag, delivery) -> {
            String message = new String(delivery.getBody(), StandardCharsets.UTF_8);
            MensajesRabbit.RespuestaIA respuesta = gson.fromJson(message, MensajesRabbit.RespuestaIA.class);
            
            System.out.println(" [x] Recibido de RabbitMQ: " + respuesta.idSolicitud);
            
            CompletableFuture<MensajesRabbit.RespuestaIA> futuro = peticionesEnVuelo.remove(respuesta.idSolicitud);
            if (futuro != null) {
                futuro.complete(respuesta); 
            }
            channel.basicAck(delivery.getEnvelope().getDeliveryTag(), false);
        };
        
        channel.basicConsume(QUEUE_RESULT_A, false, deliverCallback, consumerTag -> {});
        System.out.println(" [*] Esperando respuestas de la IA en " + QUEUE_RESULT_A);
    }

    
}